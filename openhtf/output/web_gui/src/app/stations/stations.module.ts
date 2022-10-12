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
 * Feature module for the main station views.
 *
 * See https://angular.io/docs/ts/latest/guide/ngmodule.html for more info
 * about modules in Angular.
 */

import { CommonModule } from '@angular/common';
import { NgModule } from '@angular/core';

import { PlugsModule } from '../plugs/plugs.module';
import { SharedModule } from '../shared/shared.module';

import { DashboardService } from './station-list/dashboard.service';
import { StationListComponent } from './station-list/station-list.component';
import { AttachmentsComponent } from './station/attachments.component';
import { HistoryComponent } from './station/history.component';
import { HistoryService } from './station/history.service';
import { LogsComponent } from './station/logs.component';
import { PhaseListComponent } from './station/phase-list.component';
import { PhaseComponent } from './station/phase.component';
import { StationComponent } from './station/station.component';
import { StationService } from './station/station.service';
import { TestSummaryComponent } from './station/test-summary.component';

@NgModule({
  imports: [
    CommonModule,
    PlugsModule,
    SharedModule,
  ],
  declarations: [
    StationListComponent,
    AttachmentsComponent,
    HistoryComponent,
    LogsComponent,
    PhaseComponent,
    PhaseListComponent,
    StationComponent,
    TestSummaryComponent,
  ],
  providers: [
    DashboardService,
    HistoryService,
    StationService,
  ],
  exports: [
    CommonModule,
    StationComponent,
    StationListComponent,
  ],
})
export class StationsModule {
}
