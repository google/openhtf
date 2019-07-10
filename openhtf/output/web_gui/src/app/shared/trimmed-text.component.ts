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
