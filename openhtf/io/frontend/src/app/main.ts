// Copyright 2016 Google Inc.All Rights Reserved.

// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at

//     http://www.apache.org/licenses/LICENSE-2.0

// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.


import {Component, OnInit} from 'angular2/core';
import {HTTP_PROVIDERS} from 'angular2/http';
import {bootstrap} from 'angular2/platform/browser';
import {
  RouteConfig,
  Router,
  RouterLink,
  RouterOutlet,
  ROUTER_PROVIDERS
} from 'angular2/router';

import {Dashboard} from './dashboard';
import {Station} from './station';
import 'file?name=/index.html!./index.html';
import 'file?name=/styles.css!./styles.css';


/** The main OpenHTF client app component. **/
@Component({
  selector: 'app',
  template: `
    <router-outlet>
    </router-outlet>
  `,
  directives: [RouterLink, RouterOutlet]
})
@RouteConfig([
  { path: '/', name: 'Dashboard', component: Dashboard },
  {path: '/station/:host/:port', name: 'Station', component: Station}
])
export class AppComponent {

  constructor(private router: Router) {}
}


bootstrap(AppComponent, [HTTP_PROVIDERS, ROUTER_PROVIDERS]);
