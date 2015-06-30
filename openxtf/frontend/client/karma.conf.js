/**
 * @fileoverview Description of this file.
 */
'use strict';

module.exports = function(karma) {
  karma.set({

    frameworks: [ 'jasmine', 'browserify' ],

    files: [ 'testonly/*.js', 'app/**/*_test.js' ],
    reporters: [ 'dots' ],

    preprocessors: {
      'app/**/*_test.js': [ 'browserify' ]
    },

    browsers: [ 'PhantomJS' ],

    singleRun: true,

    // browserify configuration
    browserify: {
      debug: true,
      transform: [ "browserify-ng-html2js" ]
    }
  });
};

