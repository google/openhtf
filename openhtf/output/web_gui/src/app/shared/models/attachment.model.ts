/**
 * Info about a file attached to a test.
 */

export class Attachment {
  mimeType: string;
  name: string;
  phaseDescriptorId: number;
  phaseName: string;
  sha1: string;

  // Using the class as the interface for its own constructor allows us to call
  // the constructor in named-argument style.
  constructor(params: Attachment) {
    Object.assign(this, params);
  }
}
