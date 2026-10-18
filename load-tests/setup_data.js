import http from 'k6/http';
import { check } from 'k6';
import {
  BASE_URL,
  ADMIN_USER,
  login,
  generateTargetPayload,
  generateReviewPayload,
  randomString,
} from './config.js';

/**
 * Забезпечує наявність пулу тестових Target у системі.
 * Якщо об'єктів у каталозі недостатньо, створює їх за допомогою облікового запису адміністратора.
 *
 * @param {string} baseUrl - Базовий URL платформи
 * @param {number} minCount - Необхідна мінімальна кількість Target
 * @returns {Array<string>} Масив UUID ідентифікаторів валідних Target
 */
export function ensureTestTargets(baseUrl = BASE_URL, minCount = 10) {
  const targetIds = [];

  // 1. Перевірка вже існуючих Target через публічний каталог
  const listRes = http.get(`${baseUrl}/api/v1/targets?size=${minCount}`);
  if (listRes.status === 200) {
    try {
      const body = listRes.json();
      const items = body.items || [];
      for (let i = 0; i < items.length; i++) {
        if (items[i] && items[i].id) {
          targetIds.push(items[i].id);
        }
      }
    } catch (e) {
      // Якщо каталог порожній або виникла помилка парсингу
    }
  }

  // Якщо об'єктів уже достатньо, повертаємо перші minCount
  if (targetIds.length >= minCount) {
    return targetIds.slice(0, minCount);
  }

  // 2. Якщо об'єктів не вистачає, авторизуємось для створення нових
  const auth = login(baseUrl, ADMIN_USER.username, ADMIN_USER.password);
  if (!auth.success || !auth.headers) {
    throw new Error(`[setup_data] Failed to login as admin (${ADMIN_USER.username}) to create test targets.`);
  }

  const toCreateCount = minCount - targetIds.length;
  console.log(`[setup_data] Found ${targetIds.length} targets, creating ${toCreateCount} more...`);

  for (let i = 0; i < toCreateCount; i++) {
    const payload = JSON.stringify(generateTargetPayload(targetIds.length + 1));
    const createRes = http.post(`${baseUrl}/api/v1/targets`, payload, {
      headers: auth.headers,
    });

    const isCreated = check(createRes, {
      'target created successfully (201)': (r) => r.status === 201,
    });

    if (isCreated) {
      const newTarget = createRes.json();
      targetIds.push(newTarget.id);

      // Опціонально створюємо один початковий відгук для об'єкта, щоб у сценаріях читання та голосування вже були дані
      const seedReviewPayload = JSON.stringify({
        score: 5,
        title: `Початковий відгук об'єкта [${randomString(4)}]`,
        content: `Початковий базовий відгук, згенерований під час підготовки даних setup_data. ID: ${randomString(8)}.`,
      });

      http.post(`${baseUrl}/api/v1/targets/${newTarget.id}/reviews`, seedReviewPayload, {
        headers: auth.headers,
        responseCallback: http.expectedStatuses(201, 409),
      });
    } else {
      console.error(`[setup_data] Error creating target: HTTP ${createRes.status} - ${createRes.body}`);
    }
  }

  return targetIds;
}

/**
 * Точка входу для самостійного запуску: k6 run load-tests/setup_data.js
 */
export default function () {
  console.log(`[setup_data] Initializing test targets at: ${BASE_URL}`);
  const targets = ensureTestTargets(BASE_URL, 10);
  console.log(`[setup_data] Total available targets: ${targets.length}`);
  targets.forEach((id, idx) => {
    console.log(`  [#${idx + 1}] UUID: ${id}`);
  });
}
