/**
 * Handles a connection to a websocket-like interface.
 *
 * A Subscription can be reused for multiple websocket connections. It can also
 * be configured to reconnect automatically. This makes Subscription useful as a
 * base class for our websocket-based services. However, it means that
 * Subscription must maintain a non-trivial amount of state information.
 */

enum SubscriptionState {
  unsubscribed,
  subscribing,
  subscribed,
  failed,   // Failed and not waiting to retry.
  waiting,  // Failed and waiting to retry.
}

import { Subject } from 'rxjs/Subject';

import { SockJsMessage, SockJsObject, SockJsService } from './sock-js.service';

export class Subscription {
  readonly messages = new Subject();
  retryTimeMs: number|null = null;  // Available when state is `waiting`.

  private currentRetryMs: number|null = null;  // retryMs with backoff.
  private retryTimeoutId: NodeJS.Timer|number|null = null;  // Timer from setTimeout().
  private sock: SockJsObject|null = null;
  private state = SubscriptionState.unsubscribed;

  // Params used by subscribeWithSavedParams().
  private url: string|null = null;
  private retryMs: number|null = null;
  private retryBackoff: number|null = null;
  private retryMax: number|null = null;

  constructor(private sockJsService: SockJsService) {}

  get hasError() {
    return (
        this.state === SubscriptionState.failed ||
        this.state === SubscriptionState.waiting);
  }

  get isSubscribing() {
    return this.state === SubscriptionState.subscribing;
  }

  refresh() {
    if (this.state === SubscriptionState.unsubscribed) {
      throw new Error('Cannot refresh subscription from state `unsubscribed`.');
    } else if (this.state === SubscriptionState.subscribing) {
      return;
    }
    this.unsubscribe();
    this.subscribeWithSavedParams();
  }

  retryNow() {
    if (this.state !== SubscriptionState.waiting) {
      throw new Error('Subscription cannot retryNow when state != `waiting`.');
    }
    this.cancelTimeout();
    this.subscribeWithSavedParams();
  }

  subscribeToUrl(
      url: string, retryMs: number|null = null, retryBackoff = 1.0,
      retryMax = Number.MAX_VALUE) {
    if (this.sock !== null) {
      this.unsubscribe();
    }
    this.url = url;
    this.retryMs = retryMs;
    this.retryBackoff = retryBackoff;
    this.retryMax = retryMax;
    this.subscribeWithSavedParams();
  }

  unsubscribe() {
    if (this.sock === null) {
      return;
    }
    console.debug(`Unsubscribing from ${this.url}.`);
    this.cancelTimeout();
    this.sock.close();  // Note: This does not trigger this.sock.onclose().
    this.currentRetryMs = null;
    this.state = SubscriptionState.unsubscribed;
  }

  private cancelTimeout() {
    if (this.retryTimeoutId !== null) {
      clearTimeout(this.retryTimeoutId as NodeJS.Timer);
      this.retryTimeoutId = null;
    }
  }

  private subscribeWithSavedParams() {
    console.debug(`Attempting to subscribe to ${this.url}.`);
    const sock = new this.sockJsService.sockJs(this.url);
    sock.onopen = () => {
      if (this.sock !== sock) {
        return;
      }
      console.debug(`Subscribed to ${this.url}.`);
      this.currentRetryMs = null;
      this.state = SubscriptionState.subscribed;
    };
    // Called if the initial attempt to connect fails, or, after subscribing,
    // if we detect that the other end of the socket has closed.
    sock.onclose = () => {
      if (this.sock !== sock) {
        return;
      }
      if (this.state === SubscriptionState.subscribed) {
        console.debug(`Subscription to ${this.url} lost.`);
      } else {
        console.debug(`Subscription to ${this.url} failed.`);
      }

      if (this.retryMs === null) {
        this.state = SubscriptionState.failed;
      } else {
        this.state = SubscriptionState.waiting;
        if (this.currentRetryMs === null) {
          this.currentRetryMs = this.retryMs;
        } else {
          this.currentRetryMs *= this.retryBackoff;
        }
        this.currentRetryMs = Math.max(this.currentRetryMs, this.retryMax);
        this.retryTimeMs = Date.now() + this.currentRetryMs;
        this.retryTimeoutId = setTimeout(() => {
          this.subscribeWithSavedParams();
        }, this.currentRetryMs);
      }
    };
    sock.onmessage = (message: SockJsMessage) => {
      if (this.sock !== sock) {
        return;
      }
      this.messages.next(message);
    };
    this.sock = sock;
    this.state = SubscriptionState.subscribing;
  }
}
