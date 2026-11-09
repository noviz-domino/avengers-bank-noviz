import assert from "node:assert/strict";
import { test } from "node:test";
import { validateSignup } from "./signup.mjs";
import { validatePinChange } from "./settings.mjs";
import { buildQuery } from "./search.mjs";

const ok = { login_id: "tester1", password: "password12", password2: "password12", name: "토니 스타크", phone: "010-1234-5678", birth_date: "1990-05-29" };

test("회원가입: 올바른 값은 통과, 서버 규칙 위반은 필드별로 잡는다", () => {
  assert.deepEqual(validateSignup(ok, "2026-11-09"), {});
  const bad = validateSignup({ login_id: "abc", password: "short", password2: "short", name: "토니1", phone: "123", birth_date: "2026-11-09" }, "2026-11-09");
  assert.deepEqual(Object.keys(bad).sort(), ["birth_date", "login_id", "name", "password", "phone"]);
  assert.ok(validateSignup({ ...ok, name: "토니  스타크" }, "2026-11-09").name);
  assert.ok(validateSignup({ ...ok, password2: "different1" }, "2026-11-09").password2);
});

test("PIN 변경: 숫자 6자리와 확인 일치, 비밀번호 필수", () => {
  assert.deepEqual(validatePinChange({ password: "pw", pin: "123456", pin2: "123456" }), {});
  assert.ok(validatePinChange({ password: "", pin: "123456", pin2: "123456" }).password);
  assert.ok(validatePinChange({ password: "pw", pin: "12345a", pin2: "12345a" }).pin);
  assert.ok(validatePinChange({ password: "pw", pin: "123456", pin2: "654321" }).pin2);
});

test("거래 검색: 비어 있는 조건은 빼고 쿼리를 만들고 잘못된 범위는 막는다", () => {
  const base = { keyword: " 카페 ", from_date: "", to_date: "", category: "카페·간식", direction: "", min_amount: "", max_amount: "5000" };
  const params = new URLSearchParams(buildQuery(base, "99").query);
  assert.equal(params.get("keyword"), "카페");
  assert.equal(params.get("category"), "카페·간식");
  assert.equal(params.get("max_amount"), "5000");
  assert.equal(params.get("before"), "99");
  assert.equal(params.has("direction"), false);
  assert.ok(buildQuery({ ...base, from_date: "2026-11-02", to_date: "2026-11-01" }).error);
  assert.ok(buildQuery({ ...base, min_amount: "9000" }).error);
  assert.ok(buildQuery({ ...base, min_amount: "-1" }).error);
});
