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
