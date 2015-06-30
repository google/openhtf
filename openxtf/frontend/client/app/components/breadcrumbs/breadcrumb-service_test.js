/**
 * Tests for the breadcrumb service.
 */

var BreadcrumbService = require('./breadcrumb-service.js');

describe('BreadcrumbService', function() {
  it('clears breadcrumbs', function() {
    var bs = new BreadcrumbService();
    bs.pushBreadcrumb('hi');
    bs.clear();
    expect(bs.getBreadcrumbString()).toEqual('');
  });

  it('pushes and pops a breadcrumb off', function() {
    var bs = new BreadcrumbService();
    bs.pushBreadcrumb('hi');
    bs.pushBreadcrumb('there');
    expect(bs.getBreadcrumbString()).toEqual('hi > there');
    bs.popBreadcrumb();
    expect(bs.getBreadcrumbString()).toEqual('hi');
  });

  it("doesn't error if popped empty", function() {
    var bs = new BreadcrumbService();
    bs.popBreadcrumb();
    expect(bs.getBreadcrumbString()).toEqual('');
  });
});
