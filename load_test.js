import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';

// 1. Setup Data: We must load the content of the poker log file once.
const rawLogData = new SharedArray('log_data', function () {
    // Note: k6 runs in its own environment; we assume test_log.txt is in the root
    return open('./test_log.txt', 'r');
});

// The content to be sent in the POST request body
const logContent = rawLogData[0]; 

// Define the traffic pattern (500 simultaneous users for 10 seconds)
export const options = {
    stages: [
        // Ramping up to 500 Virtual Users (VUs) over 5 seconds
        { duration: '5s', target: 500 },
        // Holding 500 VUs steady for 10 seconds
        { duration: '10s', target: 500 },
        // Ramping down to 0 VUs over 5 seconds
        { duration: '5s', target: 0 },
    ],
    // Failure condition: if any request fails or takes longer than 200ms, the test fails.
    thresholds: {
        http_req_failed: ['rate<0.01'],  // Less than 1% failure rate
        http_req_duration: ['p(95)<200'], // 95% of requests must complete in under 200ms
    },
};

// 2. The Main Test Function
export default function () {
    const url = 'http://localhost:8080/api/upload';

    // Build the request body with the file content
    const data = {
        file: http.file(logContent, 'test_log.txt', 'text/plain'),
    };

    const res = http.post(url, data);

    // Assert that the API accepted the job
    check(res, {
        'is status 202': (r) => r.status === 202,
        'has job_ids array': (r) => JSON.parse(r.body).job_ids.length > 0,
    });

    sleep(0.5); // Pause between requests
}