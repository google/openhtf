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
 * Text element whose length can be limited with expand/collapse functionality.
 */

import { Component, Input } from '@angular/core';

const ellipsis = '…';
const template = `
  {{ trimmedContent }}
  <button *ngIf="buttonLabel !== null" type="button" class="htf-link-button"
          (click)="onClick()">
    {{ buttonLabel }}
  </button>
`;

@Component({
  selector: 'htf-trimmed-text',
  template,
})
export class TrimmedTextComponent {
  @Input() maxChars: number;
  @Input() content: string|null|undefined;

  private expanded = false;

  get buttonLabel() {
    if (!this.content || this.content.length <= this.maxChars) {
      return null;
    }
    return this.expanded ? 'collapse' : 'expand';
  }

  get trimmedContent() {
    if (!this.content || this.expanded ||
        this.content.length <= this.maxChars) {
      return this.content;
    }
    return this.content.slice(0, this.maxChars - ellipsis.length) + ellipsis;
  }

  onClick() {
    this.expanded = !this.expanded;
  }
}
