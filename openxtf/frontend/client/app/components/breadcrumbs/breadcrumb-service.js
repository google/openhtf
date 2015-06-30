/**
 * @fileoverview A service for stashing the current breadcrumbs.
 *
 * It's not a very complicated service, it expects the different places to
 * set their own fully qualified breadcrumbs and does no tracking.
 */

function BreadcrumbService() {
  this.breadcrumbs = [];
}

/** Clears the list of breadcrumbs completely. */
BreadcrumbService.prototype.clear = function() {
  this.breadcrumbs = [];
};

/** Pops a breadcrumb off of the end. */
BreadcrumbService.prototype.popBreadcrumb = function() {
  this.breadcrumbs.pop();
};

/** Pushes a breadcrumb onto the stack. */
BreadcrumbService.prototype.pushBreadcrumb = function(breadcrumb, opt_link) {
  this.breadcrumbs.push({ text: breadcrumb, link: opt_link });
};

/** Retrieves a breadcrumb string. */
BreadcrumbService.prototype.getBreadcrumbs = function() {
  return this.breadcrumbs;
};

module.exports = BreadcrumbService;
