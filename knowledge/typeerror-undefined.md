Title: TypeError: Cannot read properties of undefined
Source: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/TypeError
Keywords: typeerror, cannot read properties of undefined, cannot read property, undefined, null, reading map, javascript, react

In JavaScript, a TypeError means a value is not of the type the code expected. "Cannot read properties of undefined" means the code tried to use a property or method (like .map) on a variable that is undefined.
Common causes: data that has not loaded yet (for example an API response), a misspelled property name, a function that returns nothing, or an array that was never initialized.
Ways to investigate: console.log the variable right before the failing line, check the line number in the stack trace, and use optional chaining (value?.map) or a default value (value || []) once you understand why it was undefined.