import { LitElement, css, html } from "lit";

import type { HomeAssistantLike } from "./types";

/**
 * Sidebar panel wrapper.
 *
 * Home Assistant mounts this element for the integration's own sidebar entry and
 * waits until it is defined, so the card never races the first render. The panel
 * adds nothing but a host for the card: every decision still comes from the
 * integration over the websocket subscription.
 */
export const PANEL_TYPE = "watering-project-panel";

export class WateringProjectPanel extends LitElement {
  static override properties = { hass: { attribute: false } };

  declare hass?: HomeAssistantLike;

  static override styles = css`
    :host {
      display: block;
    }

    watering-project-card {
      display: block;
    }
  `;

  protected override render() {
    return html`<watering-project-card .hass=${this.hass}></watering-project-card>`;
  }
}
