/**
 * Tests for the param status directive.
 */

var directive = require('./param-status-directive.js');
var proto = require('openhtf-proto').openhtf;

describe('ParamStatusDirective', function() {
  function makeScope() {
    return {
      realstatus: proto.Status.PASS,
      status: function() { return this.realstatus; }
    };
  }
  var Controller = directive().controller;

  it('returns the status text', function() {
    var $scope = makeScope();
    var c = new Controller($scope);
    expect(c.getStatusText()).toEqual('pass');
    $scope.realstatus = proto.Status.TIMEOUT;
    expect(c.getStatusText()).toEqual('not set');
  });

  it('returns the status class if unset', function() {
    var $scope = makeScope();
    var c = new Controller($scope);
    expect(c.getStatusClass()).toEqual('station-param-pass');
    $scope.realstatus = proto.Status.TIMEOUT;
    expect(c.getStatusClass()).toEqual('station-param-unset');
  });
});
