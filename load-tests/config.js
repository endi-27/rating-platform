import http from 'k6/http';
import { check } from 'k6';

// 1. Базовий URL платформи
export const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:80';

// 2. Облікові дані супер-адміністратора
export const ADMIN_USER = {
  username: __ENV.ADMIN_USERNAME || 'super_admin',
  password: __ENV.ADMIN_PASSWORD || 'super_admin',
};

export const SUPERADMIN_USERNAME = ADMIN_USER.username;
export const SUPERADMIN_PASSWORD = ADMIN_USER.password;

// 3. Стандартний ступеневий профіль навантаження (Staging stages)
export const stagingStages = [
  { duration: '10s', target: 10 },  // Warm-up & 10 VUs
  { duration: '15s', target: 25 },  // Ступінь 25 VUs
  { duration: '15s', target: 50 },  // Ступінь 50 VUs
  { duration: '15s', target: 100 }, // Ступінь 100 VUs
  { duration: '20s', target: 200 }, // Ступінь 200 VUs (стрес/насичення)
  { duration: '5s', target: 0 },    // Cooldown
];

// 4. Пороги якості тестування (Thresholds)
export const defaultThresholds = {
  http_req_failed: ['rate<0.05'], // помилок менше 5%
  http_req_duration: ['p(95)<1000'], // p95 < 1000ms
};

// 5. Допоміжні функції

/**
 * Авторизація користувача з витягуванням access_token з HttpOnly cookie або заголовків.
 *
 * @param {string} baseUrl - Базовий URL платформи
 * @param {string} username - Логін користувача
 * @param {string} password - Пароль користувача
 * @returns {object} { success, accessToken, headers, res }
 */
export function login(baseUrl = BASE_URL, username = SUPERADMIN_USERNAME, password = SUPERADMIN_PASSWORD) {
  const url = `${baseUrl}/api/v1/auth/login`;
  const payload = JSON.stringify({
    username: username,
    password: password,
    is_remember_me: false,
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
    },
  };

  const res = http.post(url, payload, params);
  const success = check(res, {
    'login status is 200': (r) => r.status === 200,
  });

  let accessToken = null;

  // 1. Спроба витягти з k6 response cookies
  if (res.cookies && res.cookies.access_token && res.cookies.access_token.length > 0) {
    accessToken = res.cookies.access_token[0].value;
  }

  // 2. Fallback: парсинг заголовка Set-Cookie
  if (!accessToken && res.headers['Set-Cookie']) {
    const rawCookie = res.headers['Set-Cookie'];
    const match = rawCookie.match(/access_token=([^;]+)/);
    if (match) {
      accessToken = match[1];
    }
  }

  const authHeaders = {
    'Content-Type': 'application/json',
  };

  if (accessToken) {
    authHeaders['Cookie'] = `access_token=${accessToken}`;
    authHeaders['Authorization'] = `Bearer ${accessToken}`;
  }

  return {
    success: success,
    accessToken: accessToken,
    headers: authHeaders,
    res: res,
  };
}

/**
 * Випадковий вибір елемента з масиву.
 *
 * @param {Array} array
 * @returns {*}
 */
export function getRandomItem(array) {
  if (!array || array.length === 0) {
    return null;
  }
  const index = Math.floor(Math.random() * array.length);
  return array[index];
}

/**
 * Генерація випадкового цілого числа в діапазоні [min, max].
 *
 * @param {number} min
 * @param {number} max
 * @returns {number}
 */
export function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

/**
 * Генерація псевдовипадкового рядка заданої довжини (латиниця та цифри).
 *
 * @param {number} length
 * @returns {string}
 */
export function randomString(length = 8) {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
  let result = '';
  for (let i = 0; i < length; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

/**
 * Генерація коректного payload для створення або оновлення відгуку.
 *
 * @param {number|null} forcedScore - Опціональна фіксована оцінка 1..5
 * @returns {object} { score, title, content }
 */
export function generateReviewPayload(forcedScore = null) {
  const score = forcedScore !== null ? forcedScore : randomInt(1, 5);
  const uid = randomString(6);
  return {
    score: score,
    title: `Навантажувальний тест [${uid}]`,
    content: `Це детальний автоматизований відгук для перевірки продуктивності системи. Ідентифікатор тесту: ${uid}_${Date.now()}. Оцінка сервісу: ${score} із 5.`,
  };
}

/**
 * Генерація валідного payload для створення Target (дотримується kebab-case слага).
 *
 * @param {number|string} index
 * @returns {object} { slug, title, category, description, metadata }
 */
export function generateTargetPayload(index = 0) {
  const uid = randomString(6).toLowerCase();
  return {
    slug: `target-bench-${Date.now()}-${uid}-${index}`,
    title: `Тестовий об'єкт ${index} (${uid})`,
    category: 'benchmark',
    description: 'Автоматично згенерований об\'єкт для навантажувального тестування k6',
    metadata: {
      environment: 'load-test',
      benchmark: true,
      index: index,
    },
  };
}
