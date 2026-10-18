import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1';

export const options = {
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  stages: __ENV.VUS && __ENV.DURATION
    ? [{ duration: __ENV.DURATION, target: parseInt(__ENV.VUS, 10) }]
    : [
        { duration: '5s', target: 10 },
        { duration: '5s', target: 25 },
        { duration: '5s', target: 50 },
        { duration: '5s', target: 100 },
        { duration: '5s', target: 200 },
      ],
  thresholds: {
    http_req_duration: ['p(95)<800', 'p(99)<1500'],
    http_req_failed: ['rate<0.05'],
  },
};

export default function () {
  const randSuffix = Math.floor(Math.random() * 1000000000);
  const username = `vu_${__VU}_${__ITER}_${randSuffix}`;

  const payload = JSON.stringify({
    username: username,
    name: `LoadUser ${__VU}_${__ITER}`,
    password: 'SecurePassword123!',
    is_remember_me: false,
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      'User-Agent': 'k6-scenario-b-write/1.0',
    },
  };

  // Високоінтенсивний запис: Реєстрація користувача (DB Trans + Hash + Redis Session)
  const res = http.post(`${BASE_URL}/api/v1/auth/register`, payload, params);

  check(res, {
    'user registered 201': (r) => r.status === 201 || r.status === 409,
    'has request-id': (r) => r.headers['X-Request-Id'] !== undefined || r.headers['x-request-id'] !== undefined,
  });

  sleep(0.01);
}
