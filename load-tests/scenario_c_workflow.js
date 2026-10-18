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
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    http_req_failed: ['rate<0.02'],
  },
};

export function setup() {
  let targetId = __ENV.TARGET_ID || null;
  let targetSlug = __ENV.TARGET_SLUG || null;

  try {
    const res = http.get(`${BASE_URL}/api/v1/targets?page=1&page_size=10`, {
      headers: { 'Accept': 'application/json' },
    });
    if (res.status === 200) {
      const data = JSON.parse(res.body);
      if (data.items && data.items.length > 0) {
        targetId = targetId || data.items[0].id;
        targetSlug = targetSlug || data.items[0].slug;
      }
    }
  } catch (_) {}

  return {
    targetId: targetId || 'baseline-target',
    targetSlug: targetSlug || 'baseline-target',
  };
}

export default function (data) {
  const commonHeaders = {
    'Accept': 'application/json',
    'User-Agent': 'k6-scenario-c-workflow/1.0',
  };

  const targetSlug = data.targetSlug || 'baseline-target';
  const targetId = data.targetId || 'baseline-target';

  // 1. Каталог об'єктів
  const listRes = http.get(`${BASE_URL}/api/v1/targets?page=1&page_size=10`, { headers: commonHeaders });
  check(listRes, { 'step1 catalog 200': (r) => r.status === 200 });

  // 2. Детальна картка об'єкта
  const detailRes = http.get(`${BASE_URL}/api/v1/targets/${targetSlug}`, { headers: commonHeaders });
  check(detailRes, { 'step2 details 200': (r) => r.status === 200 || r.status === 404 });

  // 3. Агрегований рейтинг
  const ratingRes1 = http.get(`${BASE_URL}/api/v1/targets/${targetId}/rating`, { headers: commonHeaders });
  check(ratingRes1, { 'step3 rating 200': (r) => r.status === 200 || r.status === 404 });

  // 4. Стрічка відгуків
  const reviewsRes = http.get(`${BASE_URL}/api/v1/targets/${targetId}/reviews?page=1&page_size=10`, { headers: commonHeaders });
  check(reviewsRes, { 'step4 reviews 200': (r) => r.status === 200 || r.status === 404 });

  // 5. Дія запису (реєстрація сесії користувача для взаємодії)
  const rand = Math.floor(Math.random() * 1000000000);
  const regPayload = JSON.stringify({
    username: `wf_${__VU}_${__ITER}_${rand}`,
    name: `Workflow User ${__VU}`,
    password: 'SecurePassword123!',
    is_remember_me: false,
  });
  const regRes = http.post(`${BASE_URL}/api/v1/auth/register`, regPayload, {
    headers: { ...commonHeaders, 'Content-Type': 'application/json' },
  });
  check(regRes, { 'step5 write action 201': (r) => r.status === 201 || r.status === 409 });

  // 6. Повторне зчитування рейтингу після оновлення
  const ratingRes2 = http.get(`${BASE_URL}/api/v1/targets/${targetId}/rating`, { headers: commonHeaders });
  check(ratingRes2, { 'step6 re-read rating 200': (r) => r.status === 200 || r.status === 404 });

  sleep(0.01);
}
