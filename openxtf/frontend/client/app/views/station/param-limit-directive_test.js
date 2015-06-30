/**
 * Tests for the param value directive.
 */

var directive = require('./param-limit-directive.js');
var proto = require('openxtf-proto').openxtf;

describe('ParamLimitDirective', function() {
  function makeScope() {
    var p = new proto.TestParameter();
    return {
      parameter: function() { return this.p; },
      p: p
    };
  }
  var Controller = directive().controller;

  it('returns numeric = if values are same', function() {
    var $scope = makeScope();
    $scope.p.numeric_minimum = $scope.p.numeric_maximum = 5;
    var c = new Controller($scope);
    expect(c.getLimit()).toEqual('x == 5');
  });

  it('returns text limit', function() {
    var $scope = makeScope();
    $scope.p.expected_text = 'hi';
    var c = new Controller($scope);
    expect(c.getLimit()).toEqual('hi');
  });

  it('returns joined limit if both numeric limits are set', function() {
    var $scope = makeScope();
    $scope.p.numeric_minimum = 5;
    $scope.p.numeric_maximum = 11;
    var c = new Controller($scope);
    expect(c.getLimit()).toEqual('5 <= x <= 11');
  });

  it('returns only one if one numeric limit is set', function() {
    var $scope = makeScope();
    $scope.p.numeric_minimum = 5;
    var c = new Controller($scope);
    expect(c.getLimit()).toEqual('5 <= x');
  });
});
