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
 * Contains classes that are re-used across the features modules.
 *
 * See https://angular.io/docs/ts/latest/guide/ngmodule.html for more info
 * about modules in Angular.
 */

import { CommonModule } from '@angular/common';
import { NgModule } from '@angular/core';
import { HttpModule } from '@angular/http';

import { ElapsedTimePipe } from './elapsed-time.pipe';
import { FocusDirective } from './focus.directive';
import { GenealogyNodeComponent } from './genealogy-node.component';
import { LogLevelToClassPipe } from './log-level-to-class.pipe';
import { ObjectToSortedValuesPipe } from './object-to-sorted-values.pipe';
import { ProgressBarComponent } from './progress-bar.component';
import { SockJsService } from './sock-js.service';
import { StatusToClassPipe, StatusToTextPipe } from './status-pipes';
import { TimeAgoPipe } from './time-ago.pipe';
import { TimeService } from './time.service';
import { TooltipDirective } from './tooltip.directive';
import { TrimmedTextComponent } from './trimmed-text.component';

@NgModule({
  imports: [
    CommonModule,
    HttpModule,
  ],
  declarations: [
    ElapsedTimePipe,
    FocusDirective,
    GenealogyNodeComponent,
    LogLevelToClassPipe,
    ObjectToSortedValuesPipe,
    ProgressBarComponent,
    StatusToClassPipe,
    StatusToTextPipe,
    TimeAgoPipe,
    TrimmedTextComponent,
    TooltipDirective,
  ],
  providers: [
    SockJsService,
    TimeService,
  ],
  exports: [
    CommonModule,
    ElapsedTimePipe,
    FocusDirective,
    GenealogyNodeComponent,
    LogLevelToClassPipe,
    ObjectToSortedValuesPipe,
    ProgressBarComponent,
    StatusToClassPipe,
    StatusToTextPipe,
    TimeAgoPipe,
    TrimmedTextComponent,
    TooltipDirective,
  ],
})
export class SharedModule {
}
