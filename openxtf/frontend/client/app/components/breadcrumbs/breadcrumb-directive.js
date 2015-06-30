/**
 * @fileoverview The directive to display the breadcrumb.
 */

function BreadcrumbDirective() {
  return {
    restrict: 'A',
    templateUrl: "breadcrumb.html",
    controller: BreadcrumbController,
    controllerAs: "BC"
  };
}
module.exports = BreadcrumbDirective;

/**
 * A controller for breadcrumbs.
 * @param {angular.Scope} $scope The angular scope
 * @param {Object} oxBreadcrumbService The ox breadcrumb service
 * @constructor
 */
function BreadcrumbController($scope, oxBreadcrumbService) {
  this.oxBreadcrumbService = oxBreadcrumbService;
}

/** @return {string} The breadcrumbs tring. */
BreadcrumbController.prototype.getBreadcrumbs = function() {
  return this.oxBreadcrumbService.getBreadcrumbs();
};
