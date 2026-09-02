/* Plain-Node unit tests for the dashboard's pure helpers.
 * Run: node static/app.test.js
 */
"use strict";

var assert = require("assert");
var app = require("./app.js");

var passed = 0;
function check(name, fn) {
  fn();
  passed++;
  console.log("  ok - " + name);
}

check("fmt formats integers with thousands separators", function () {
  assert.strictEqual(app.fmt(20000), "20,000");
  assert.strictEqual(app.fmt(15234.5), "15,234.5");
});

check("fmt guards null/NaN", function () {
  assert.strictEqual(app.fmt(null), "0");
  assert.strictEqual(app.fmt(NaN), "0");
});

check("kpiCard passes a pre-formatted percent string through unchanged", function () {
  // Regression: kpiCard used to run every value through fmt(), turning "75%" into "0".
  var html = app.kpiCard(75 + "%", "نسبة الاستهلاك", "warn");
  assert.ok(html.indexOf(">75%<") !== -1, html);
});

check("kpiCard still formats numeric values", function () {
  var html = app.kpiCard(20000, "الميزانية (EGP)");
  assert.ok(html.indexOf("20,000") !== -1, html);
});

check("kpiCard handles 0% without collapsing to a bare 0", function () {
  var html = app.kpiCard(0 + "%", "نسبة الاستهلاك");
  assert.ok(html.indexOf(">0%<") !== -1, html);
});

check("CATEGORIES includes the 'أخرى' fallback bucket", function () {
  assert.ok(Object.prototype.hasOwnProperty.call(app.CATEGORIES, "أخرى"));
  assert.strictEqual(app.CATEGORIES["أخرى"], 0);
});

check("parseCsvDate handles ISO and slash formats", function () {
  assert.strictEqual(app.parseCsvDate("2026-09-01").getFullYear(), 2026);
  assert.strictEqual(app.parseCsvDate("9/1/2026").getMonth(), 8);
  assert.strictEqual(app.parseCsvDate(""), null);
});

console.log("\n" + passed + " dashboard tests passed");
