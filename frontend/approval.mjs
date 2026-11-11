// 서버 승인 대기 요청(이체·예금 개설·카드 정지 해제)을 PIN으로 승인하는 공통 창.
// 화면은 서버가 만든 summary만 보여 주고, 완료는 서버 실행 성공 뒤에만 알린다.
// 예산을 넘는 건(needs_budget_reason)은 영향 문장을 보여 주고 사유(필수)와 "긴급"을 함께 보낸다 (ADR 0022).
import { api, ApiError } from "./api.mjs";

const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const STYLE = `
dialog.approval { border: 0; border-radius: 20px; padding: 24px 20px; width: min(360px, calc(100vw - 32px)); color: var(--navy, #10233b); }
dialog.approval::backdrop { background: rgb(16 35 59 / .45); }
dialog.approval h2 { margin-bottom: 8px; }
dialog.approval .summary { background: var(--cream, #f8f1e5); border-radius: 12px; padding: 12px; margin: 12px 0; white-space: pre-line; }
dialog.approval label { display: grid; gap: 6px; margin: 10px 0; font-weight: 600; }
dialog.approval input { padding: 12px; border: 1px solid var(--line, #e2e8ed); border-radius: 10px; letter-spacing: .3em; }
dialog.approval .error { color: #b84039; min-height: 1.4em; }
dialog.approval .budget { background: #fdecea; color: #8a2d27; border-radius: 12px; padding: 10px 12px; margin: 8px 0; }
dialog.approval input[name="reason"] { letter-spacing: normal; }
dialog.approval label.check { display: flex; align-items: center; gap: 8px; font-weight: 500; }
dialog.approval .row { display: flex; gap: 8px; margin-top: 12px; }
dialog.approval .row button { flex: 1; padding: 12px; border-radius: 12px; border: 1px solid var(--line, #e2e8ed); background: #fff; }
dialog.approval .row button.primary { background: var(--navy, #10233b); color: #fff; border-color: transparent; }
`;

function ensureStyle() {
  if (document.getElementById("approval-style")) return;
  const style = document.createElement("style");
  style.id = "approval-style";
  style.textContent = STYLE;
  document.head.append(style);
}

/**
 * 승인 창을 열고 결과를 돌려준다.
 * @param {string} actionId 서버가 준 action_id (202 응답의 data.action_id)
 * @returns {Promise<{status: "EXECUTED", action: object} | {status: "REJECTED"} | {status: "FAILED", error: ApiError}>}
 */
export async function openApproval(actionId) {
  ensureStyle();
  const [action, me] = await Promise.all([
    api("/approvals/" + encodeURIComponent(actionId)).then((r) => r.data),
    api("/users/me").then((r) => r.data),
  ]);
  const dialog = document.createElement("dialog");
  dialog.className = "approval";
  dialog.setAttribute("aria-labelledby", "approval-title");
  document.body.append(dialog);

  return new Promise((resolve) => {
    let hasPin = me.has_pin;
    const finish = (result) => { dialog.close(); dialog.remove(); resolve(result); };
    const draw = (error = "") => {
      dialog.innerHTML = '<form method="dialog" data-form="approval">'
        + '<h2 id="approval-title">' + (hasPin ? "PIN으로 승인해 주세요" : "거래 PIN을 먼저 등록해 주세요") + "</h2>"
        + '<div class="summary">' + esc(action.summary) + "</div>"
        + (action.needs_budget_reason
          ? '<p class="budget" role="note">' + esc(action.budget_impact) + "</p>"
            + '<label>예산을 넘기는 이유 (꼭 적어 주세요)<input name="reason" required maxlength="200" autocomplete="off"></label>'
            + '<label class="check"><input name="emergency" type="checkbox"> 긴급 (경조사, 급한 수리 등)</label>'
          : "")
        + (hasPin ? ""
          : '<label>로그인 비밀번호<input name="password" type="password" required autocomplete="current-password"></label>')
        + '<label>' + (hasPin ? "거래 PIN 6자리" : "새 거래 PIN 6자리")
        + '<input name="pin" type="password" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" required autocomplete="off"></label>'
        + '<p class="error" role="alert">' + esc(error) + "</p>"
        + '<div class="row"><button type="button" data-approval="cancel">취소</button>'
        + '<button type="submit" class="primary">' + (hasPin ? "승인" : "등록하고 승인") + "</button></div></form>";
      dialog.querySelector("input")?.focus();
    };

    dialog.addEventListener("cancel", (event) => { event.preventDefault(); reject(); });
    dialog.addEventListener("click", (event) => { if (event.target.closest('[data-approval="cancel"]')) reject(); });
    dialog.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = new FormData(event.target);
      const pin = form.get("pin");
      dialog.querySelectorAll("button").forEach((b) => { b.disabled = true; });
      try {
        if (!hasPin) {
          await api("/users/me/pin", { method: "PUT", body: { password: form.get("password"), pin } });
          hasPin = true;
        }
        const body = action.needs_budget_reason
          ? { pin, reason: String(form.get("reason") || "").trim(), emergency: form.get("emergency") === "on" }
          : { pin };
        const done = await api("/approvals/" + encodeURIComponent(actionId) + "/approve", { method: "POST", body });
        finish({ status: "EXECUTED", action: done.data });
      } catch (error) {
        if (!(error instanceof ApiError)) throw error;
        // PIN 오입력·비밀번호 오류는 다시 입력, 그 밖(잠김·만료·이미 처리·재검사 실패)은 끝낸다
        if (["INVALID_PIN", "INVALID_PASSWORD", "BUDGET_REASON_REQUIRED"].includes(error.code) || error.status === 422) draw(error.message);
        else finish({ status: "FAILED", error });
      }
    });

    async function reject() {
      await api("/approvals/" + encodeURIComponent(actionId) + "/reject", { method: "POST" }).catch(() => {});
      finish({ status: "REJECTED" });
    }

    draw();
    dialog.showModal();
  });
}
