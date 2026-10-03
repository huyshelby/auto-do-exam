/**
 * Mô phỏng chuỗi biến cố chuột chuẩn trình duyệt (Canonical Native Event Cascade)
 */
import { sleep } from './pacing.js';

export async function dispatchRealisticClick(element) {
  if (!element) return;

  const rect = element.getBoundingClientRect();
  // Điểm chạm ngẫu nhiên ở khu vực trung tâm phần tử (từ 30% đến 70% kích thước)
  const offsetX = rect.width * (0.30 + Math.random() * 0.40);
  const offsetY = rect.height * (0.30 + Math.random() * 0.40);
  const clientX = rect.left + offsetX;
  const clientY = rect.top + offsetY;

  const baseProps = {
    bubbles: true,
    cancelable: true,
    composed: true,
    view: window,
    clientX: clientX,
    clientY: clientY,
    screenX: (window.screenX || 0) + clientX,
    screenY: (window.screenY || 0) + clientY,
  };

  // 1. Hover & Move
  element.dispatchEvent(new PointerEvent('pointerover', baseProps));
  element.dispatchEvent(new MouseEvent('mouseover', baseProps));

  element.dispatchEvent(new PointerEvent('pointermove', baseProps));
  element.dispatchEvent(new MouseEvent('mousemove', baseProps));

  await sleep(15 + Math.random() * 25);

  // 2. Mouse Press (buttons: 1, button: 0)
  const downProps = { ...baseProps, button: 0, buttons: 1 };
  element.dispatchEvent(new PointerEvent('pointerdown', downProps));
  element.dispatchEvent(new MouseEvent('mousedown', downProps));

  if (typeof element.focus === 'function') {
    try { element.focus(); } catch (e) {}
  }

  // 3. Dwell Time (Thời gian đè chuột: 60ms - 110ms)
  await sleep(60 + Math.random() * 50);

  // 4. Mouse Release (buttons: 0, button: 0)
  const upProps = { ...baseProps, button: 0, buttons: 0 };
  element.dispatchEvent(new PointerEvent('pointerup', upProps));
  element.dispatchEvent(new MouseEvent('mouseup', upProps));

  // 5. Final Click Event (detail: 1)
  const clickProps = { ...upProps, detail: 1 };
  element.dispatchEvent(new MouseEvent('click', clickProps));

  // 6. Kích hoạt sự kiện input/change nếu là phần tử radio/checkbox
  const radio = element.querySelector('input[type="radio"], input[type="checkbox"]') ||
                (element.tagName === 'INPUT' ? element : null);
  if (radio) {
    radio.checked = true;
    radio.dispatchEvent(new Event('change', { bubbles: true }));
    radio.dispatchEvent(new Event('input', { bubbles: true }));
  }
}
