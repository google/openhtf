/**
 * Tests for the capitalize filter.
 */

var angular = require('angular');
var angularmock = require('angular-mocks');
var capitalize = require('./capitalize-filter.js');

describe('Capitalize', function() {
  beforeEach(function() {
    window.module(capitalize.name);
  });

  it('capitalizes the word', inject(function(capitalizeFilter) {
    expect(capitalizeFilter('hello there')).toEqual('Hello there');
  }));
});
