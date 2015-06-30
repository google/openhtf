/**
 * Tests for the param value directive.
 */

var directive = require('./param-value-directive.js');
var proto = require('openxtf-proto').openxtf;

describe('ParamValueDirective', function() {
  function makeScope() {
    var p = new proto.TestParameter();
    return {
      parameter: function() { return this.realparameter; },
      realparameter: p
    };
  }
  var Controller = directive().controller;

  it('returns empty if nothing set', function() {
    var $scope = makeScope();
    var c = new Controller($scope);
    expect(c.getValue()).toEqual('');
  });

  it('returns text value if set', function() {
    var $scope = makeScope();
    $scope.realparameter.text_value = 'hi';
    var c = new Controller($scope);
    expect(c.getValue()).toEqual('hi');
  });

  it('returns numeric value if set or both set', function() {
    var $scope = makeScope();
    $scope.realparameter.numeric_value = 3;
    var c = new Controller($scope);
    expect(c.getValue()).toEqual(3);

    $scope.realparameter.text_value = 'hi';
    expect(c.getValue()).toEqual(3);
  });
});
