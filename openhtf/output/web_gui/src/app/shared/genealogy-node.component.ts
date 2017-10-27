/**
 * Recursive component representing a node in a genealogy tree.
 */

import { Component, Input, OnInit } from '@angular/core';
import { GenealogyTreeNode } from './genealogy.model';

@Component({
  selector: 'htf-genealogy-node',
  templateUrl: './genealogy-node.component.html',
  styleUrls: ['./genealogy-node.component.scss'],
})
export class GenealogyNodeComponent implements OnInit {
  @Input() isFirst: boolean;
  @Input() isRoot: boolean;
  @Input() node: GenealogyTreeNode;
  @Input() maxDepth: number|null;
  childMaxDepth: number|null;

  ngOnInit() {
    if (this.maxDepth === null) {
      this.childMaxDepth = null;
    } else {
      this.childMaxDepth = this.maxDepth - 1;
    }

    // Assume isRoot is true unless specified false.
    if (typeof this.isRoot === 'undefined') {
      this.isRoot = true;
    }
  }
}
