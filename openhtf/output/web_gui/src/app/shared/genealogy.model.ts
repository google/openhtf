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
 * Genealogy/assembly state and operations.
 *
 * TODO(kenadia): We may be able to generate these interfaces from the
 * proto definition.
 */

export interface GenealogyComponent {
  instance_name: string;
  part_number: string;
  serial: string;
}

export interface GenealogyTreeNode {
  children: GenealogyTreeNode[];
  component: GenealogyComponent;
}

export interface AssemblyEvent {
  child?: GenealogyComponent;
  op: AssemblyOperation;
  target: GenealogyComponent;
}

// From assembly_event.proto.
export enum AssemblyOperation {
  attach = 0,
  detach = 1,
  create = 2,
  update = 3,
  detach_all_children = 4,
}
