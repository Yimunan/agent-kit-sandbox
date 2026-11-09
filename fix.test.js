const { absDiff } = require('./calc');

test('absDiff negative', () => {
  expect(absDiff(1, 3)).toBe(2);
});
