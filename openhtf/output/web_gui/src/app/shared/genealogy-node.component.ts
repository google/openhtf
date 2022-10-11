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
