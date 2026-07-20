/**
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/**
 * The root module, responsible for orchestrating the application as a whole.
 *
 * See https://angular.io/docs/ts/latest/guide/ngmodule.html for more info
 * about modules in Angular.
 */

import { NgModule } from '@angular/core';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { BrowserModule } from '@angular/platform-browser';
import { provideHttpClient, withInterceptorsFromDi, withXhr } from '@angular/common/http';
import { FormsModule } from '@angular/forms';

import { AppComponent } from './app.component';

/* Our Modules */
import { CoreModule } from './core/core.module';
import { PlugsModule } from './plugs/plugs.module';
import { SharedModule } from './shared/shared.module';
import { StationsModule } from './stations/stations.module';

@NgModule({
  imports: [
    BrowserAnimationsModule,
    BrowserModule,
    FormsModule,
    // Our modules
    CoreModule,
    PlugsModule,
    SharedModule,
    StationsModule
  ],
  providers: [provideHttpClient(withXhr(), withInterceptorsFromDi())],
  declarations: [
    AppComponent,
  ],
  bootstrap: [
    AppComponent
  ],
})
export class AppModule { }

