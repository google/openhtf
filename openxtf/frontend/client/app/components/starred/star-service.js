/**
 * @fileoverview A service which tracks starred stations.
 */

var STAR_STORAGE_KEY = 'openxtf.client.starred';

var FAKE_STORE = {setItem: function() {}, getItem: function() {}};

function getLocalStorage() {
  if (window.localStorage) {
    return window.localStorage;
  } else {
    return FAKE_STORE;
  }
}

/** @constructor */
function StarService($rootScope) {
  this.$rootScope = $rootScope;
  this.storage = getLocalStorage();
  var instorage = this.storage.getItem(STAR_STORAGE_KEY);
  try {
    this.starred = JSON.parse(instorage) || {};
  } catch (err) {
    this.starred = {};
  }
}
module.exports = StarService;

/**
 * Toggles the station.
 * @param {string} stationName
 */
StarService.prototype.toggleStarred = function(stationName) {
  if (stationName in this.starred) {
    delete this.starred[stationName];
  } else {
    this.starred[stationName] = true;
  }

  this.storage.setItem(STAR_STORAGE_KEY, JSON.stringify(this.starred));
};

/**
 * @param {string} stationName
 * @return {boolean} True if this station is starred.
 */
StarService.prototype.isStarred = function(stationName) {
  return !!this.starred[stationName];
};

/** @return {string} Returns the list of starred stations. */
StarService.prototype.getStarred = function() {
  return Object.keys(this.starred);
};
