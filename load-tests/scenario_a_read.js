import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1';

// Налаштування профілю навантаження k6
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
    http_req_duration: ['p(95)<300', 'p(99)<600'],
    http_req_failed: ['rate<0.01'],
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
  const params = {
    headers: {
      'Accept': 'application/json',
      'User-Agent': 'k6-scenario-a-read/1.0',
    },
  };

  // 1. Каталог об'єктів (Read-heavy, пагінація)
  const listRes = http.get(`${BASE_URL}/api/v1/targets?page=1&page_size=20`, params);
  check(listRes, {
    'catalog status 200': (r) => r.status === 200,
  });

  // 2. Детальна картка об'єкта (Redis Cache Layer)
  const slug = data.targetSlug || 'baseline-target';
  const detailRes = http.get(`${BASE_URL}/api/v1/targets/${slug}`, params);
  check(detailRes, {
    'target details 200': (r) => r.status === 200 || r.status === 404,
  });

  // 3. Агрегований рейтинг об'єкта (Redis Cache Layer)
  if (data.targetId) {
    const ratingRes = http.get(`${BASE_URL}/api/v1/targets/${data.targetId}/rating`, params);
    check(ratingRes, {
      'target rating 200': (r) => r.status === 200 || r.status === 404,
    });

    // 4. Стрічка відгуків об'єкта (Database Read Query)
    const reviewsRes = http.get(`${BASE_URL}/api/v1/targets/${data.targetId}/reviews?page=1&page_size=10`, params);
    check(reviewsRes, {
      'target reviews 200': (r) => r.status === 200 || r.status === 404,
    });
  }

  sleep(0.01);
}
