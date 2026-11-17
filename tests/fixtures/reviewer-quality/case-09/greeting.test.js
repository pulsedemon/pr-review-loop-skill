const assert = require("node:assert/strict");
const test = require("node:test");

const { greeting } = require("./greeting");

test("greeting addresses the name", () => {
  assert.equal(greeting("Ada"), "Hello, Ada");
});
