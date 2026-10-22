const T = globalThis, B = T.ShadowRoot && (T.ShadyCSS === void 0 || T.ShadyCSS.nativeShadow) && "adoptedStyleSheets" in Document.prototype && "replace" in CSSStyleSheet.prototype, D = /* @__PURE__ */ Symbol(), K = /* @__PURE__ */ new WeakMap();
let dt = class {
  constructor(t, e, s) {
    if (this._$cssResult$ = !0, s !== D) throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");
    this.cssText = t, this.t = e;
  }
  get styleSheet() {
    let t = this.o;
    const e = this.t;
    if (B && t === void 0) {
      const s = e !== void 0 && e.length === 1;
      s && (t = K.get(e)), t === void 0 && ((this.o = t = new CSSStyleSheet()).replaceSync(this.cssText), s && K.set(e, t));
    }
    return t;
  }
  toString() {
    return this.cssText;
  }
};
const mt = (r) => new dt(typeof r == "string" ? r : r + "", void 0, D), ct = (r, ...t) => {
  const e = r.length === 1 ? r[0] : t.reduce((s, i, n) => s + ((o) => {
    if (o._$cssResult$ === !0) return o.cssText;
    if (typeof o == "number") return o;
    throw Error("Value passed to 'css' function must be a 'css' function result: " + o + ". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.");
  })(i) + r[n + 1], r[0]);
  return new dt(e, r, D);
}, $t = (r, t) => {
  if (B) r.adoptedStyleSheets = t.map((e) => e instanceof CSSStyleSheet ? e : e.styleSheet);
  else for (const e of t) {
    const s = document.createElement("style"), i = T.litNonce;
    i !== void 0 && s.setAttribute("nonce", i), s.textContent = e.cssText, r.appendChild(s);
  }
}, J = B ? (r) => r : (r) => r instanceof CSSStyleSheet ? ((t) => {
  let e = "";
  for (const s of t.cssRules) e += s.cssText;
  return mt(e);
})(r) : r;
const { is: yt, defineProperty: gt, getOwnPropertyDescriptor: bt, getOwnPropertyNames: vt, getOwnPropertySymbols: At, getPrototypeOf: wt } = Object, H = globalThis, Z = H.trustedTypes, xt = Z ? Z.emptyScript : "", St = H.reactiveElementPolyfillSupport, E = (r, t) => r, L = { toAttribute(r, t) {
  switch (t) {
    case Boolean:
      r = r ? xt : null;
      break;
    case Object:
    case Array:
      r = r == null ? r : JSON.stringify(r);
  }
  return r;
}, fromAttribute(r, t) {
  let e = r;
  switch (t) {
    case Boolean:
      e = r !== null;
      break;
    case Number:
      e = r === null ? null : Number(r);
      break;
    case Object:
    case Array:
      try {
        e = JSON.parse(r);
      } catch {
        e = null;
      }
  }
  return e;
} }, ht = (r, t) => !yt(r, t), G = { attribute: !0, type: String, converter: L, reflect: !1, useDefault: !1, hasChanged: ht };
Symbol.metadata ??= /* @__PURE__ */ Symbol("metadata"), H.litPropertyMetadata ??= /* @__PURE__ */ new WeakMap();
let b = class extends HTMLElement {
  static addInitializer(t) {
    this._$Ei(), (this.l ??= []).push(t);
  }
  static get observedAttributes() {
    return this.finalize(), this._$Eh && [...this._$Eh.keys()];
  }
  static createProperty(t, e = G) {
    if (e.state && (e.attribute = !1), this._$Ei(), this.prototype.hasOwnProperty(t) && ((e = Object.create(e)).wrapped = !0), this.elementProperties.set(t, e), !e.noAccessor) {
      const s = /* @__PURE__ */ Symbol(), i = this.getPropertyDescriptor(t, s, e);
      i !== void 0 && gt(this.prototype, t, i);
    }
  }
  static getPropertyDescriptor(t, e, s) {
    const { get: i, set: n } = bt(this.prototype, t) ?? { get() {
      return this[e];
    }, set(o) {
      this[e] = o;
    } };
    return { get: i, set(o) {
      const c = i?.call(this);
      n?.call(this, o), this.requestUpdate(t, c, s);
    }, configurable: !0, enumerable: !0 };
  }
  static getPropertyOptions(t) {
    return this.elementProperties.get(t) ?? G;
  }
  static _$Ei() {
    if (this.hasOwnProperty(E("elementProperties"))) return;
    const t = wt(this);
    t.finalize(), t.l !== void 0 && (this.l = [...t.l]), this.elementProperties = new Map(t.elementProperties);
  }
  static finalize() {
    if (this.hasOwnProperty(E("finalized"))) return;
    if (this.finalized = !0, this._$Ei(), this.hasOwnProperty(E("properties"))) {
      const e = this.properties, s = [...vt(e), ...At(e)];
      for (const i of s) this.createProperty(i, e[i]);
    }
    const t = this[Symbol.metadata];
    if (t !== null) {
      const e = litPropertyMetadata.get(t);
      if (e !== void 0) for (const [s, i] of e) this.elementProperties.set(s, i);
    }
    this._$Eh = /* @__PURE__ */ new Map();
    for (const [e, s] of this.elementProperties) {
      const i = this._$Eu(e, s);
      i !== void 0 && this._$Eh.set(i, e);
    }
    this.elementStyles = this.finalizeStyles(this.styles);
  }
  static finalizeStyles(t) {
    const e = [];
    if (Array.isArray(t)) {
      const s = new Set(t.flat(1 / 0).reverse());
      for (const i of s) e.unshift(J(i));
    } else t !== void 0 && e.push(J(t));
    return e;
  }
  static _$Eu(t, e) {
    const s = e.attribute;
    return s === !1 ? void 0 : typeof s == "string" ? s : typeof t == "string" ? t.toLowerCase() : void 0;
  }
  constructor() {
    super(), this._$Ep = void 0, this.isUpdatePending = !1, this.hasUpdated = !1, this._$Em = null, this._$Ev();
  }
  _$Ev() {
    this._$ES = new Promise((t) => this.enableUpdating = t), this._$AL = /* @__PURE__ */ new Map(), this._$E_(), this.requestUpdate(), this.constructor.l?.forEach((t) => t(this));
  }
  addController(t) {
    (this._$EO ??= /* @__PURE__ */ new Set()).add(t), this.renderRoot !== void 0 && this.isConnected && t.hostConnected?.();
  }
  removeController(t) {
    this._$EO?.delete(t);
  }
  _$E_() {
    const t = /* @__PURE__ */ new Map(), e = this.constructor.elementProperties;
    for (const s of e.keys()) this.hasOwnProperty(s) && (t.set(s, this[s]), delete this[s]);
    t.size > 0 && (this._$Ep = t);
  }
  createRenderRoot() {
    const t = this.shadowRoot ?? this.attachShadow(this.constructor.shadowRootOptions);
    return $t(t, this.constructor.elementStyles), t;
  }
  connectedCallback() {
    this.renderRoot ??= this.createRenderRoot(), this.enableUpdating(!0), this._$EO?.forEach((t) => t.hostConnected?.());
  }
  enableUpdating(t) {
  }
  disconnectedCallback() {
    this._$EO?.forEach((t) => t.hostDisconnected?.());
  }
  attributeChangedCallback(t, e, s) {
    this._$AK(t, s);
  }
  _$ET(t, e) {
    const s = this.constructor.elementProperties.get(t), i = this.constructor._$Eu(t, s);
    if (i !== void 0 && s.reflect === !0) {
      const n = (s.converter?.toAttribute !== void 0 ? s.converter : L).toAttribute(e, s.type);
      this._$Em = t, n == null ? this.removeAttribute(i) : this.setAttribute(i, n), this._$Em = null;
    }
  }
  _$AK(t, e) {
    const s = this.constructor, i = s._$Eh.get(t);
    if (i !== void 0 && this._$Em !== i) {
      const n = s.getPropertyOptions(i), o = typeof n.converter == "function" ? { fromAttribute: n.converter } : n.converter?.fromAttribute !== void 0 ? n.converter : L;
      this._$Em = i;
      const c = o.fromAttribute(e, n.type);
      this[i] = c ?? this._$Ej?.get(i) ?? c, this._$Em = null;
    }
  }
  requestUpdate(t, e, s, i = !1, n) {
    if (t !== void 0) {
      const o = this.constructor;
      if (i === !1 && (n = this[t]), s ??= o.getPropertyOptions(t), !((s.hasChanged ?? ht)(n, e) || s.useDefault && s.reflect && n === this._$Ej?.get(t) && !this.hasAttribute(o._$Eu(t, s)))) return;
      this.C(t, e, s);
    }
    this.isUpdatePending === !1 && (this._$ES = this._$EP());
  }
  C(t, e, { useDefault: s, reflect: i, wrapped: n }, o) {
    s && !(this._$Ej ??= /* @__PURE__ */ new Map()).has(t) && (this._$Ej.set(t, o ?? e ?? this[t]), n !== !0 || o !== void 0) || (this._$AL.has(t) || (this.hasUpdated || s || (e = void 0), this._$AL.set(t, e)), i === !0 && this._$Em !== t && (this._$Eq ??= /* @__PURE__ */ new Set()).add(t));
  }
  async _$EP() {
    this.isUpdatePending = !0;
    try {
      await this._$ES;
    } catch (e) {
      Promise.reject(e);
    }
    const t = this.scheduleUpdate();
    return t != null && await t, !this.isUpdatePending;
  }
  scheduleUpdate() {
    return this.performUpdate();
  }
  performUpdate() {
    if (!this.isUpdatePending) return;
    if (!this.hasUpdated) {
      if (this.renderRoot ??= this.createRenderRoot(), this._$Ep) {
        for (const [i, n] of this._$Ep) this[i] = n;
        this._$Ep = void 0;
      }
      const s = this.constructor.elementProperties;
      if (s.size > 0) for (const [i, n] of s) {
        const { wrapped: o } = n, c = this[i];
        o !== !0 || this._$AL.has(i) || c === void 0 || this.C(i, void 0, n, c);
      }
    }
    let t = !1;
    const e = this._$AL;
    try {
      t = this.shouldUpdate(e), t ? (this.willUpdate(e), this._$EO?.forEach((s) => s.hostUpdate?.()), this.update(e)) : this._$EM();
    } catch (s) {
      throw t = !1, this._$EM(), s;
    }
    t && this._$AE(e);
  }
  willUpdate(t) {
  }
  _$AE(t) {
    this._$EO?.forEach((e) => e.hostUpdated?.()), this.hasUpdated || (this.hasUpdated = !0, this.firstUpdated(t)), this.updated(t);
  }
  _$EM() {
    this._$AL = /* @__PURE__ */ new Map(), this.isUpdatePending = !1;
  }
  get updateComplete() {
    return this.getUpdateComplete();
  }
  getUpdateComplete() {
    return this._$ES;
  }
  shouldUpdate(t) {
    return !0;
  }
  update(t) {
    this._$Eq &&= this._$Eq.forEach((e) => this._$ET(e, this[e])), this._$EM();
  }
  updated(t) {
  }
  firstUpdated(t) {
  }
};
b.elementStyles = [], b.shadowRootOptions = { mode: "open" }, b[E("elementProperties")] = /* @__PURE__ */ new Map(), b[E("finalized")] = /* @__PURE__ */ new Map(), St?.({ ReactiveElement: b }), (H.reactiveElementVersions ??= []).push("2.1.2");
const I = globalThis, Y = (r) => r, R = I.trustedTypes, X = R ? R.createPolicy("lit-html", { createHTML: (r) => r }) : void 0, ut = "$lit$", m = `lit$${Math.random().toFixed(9).slice(2)}$`, pt = "?" + m, Et = `<${pt}>`, g = document, k = () => g.createComment(""), P = (r) => r === null || typeof r != "object" && typeof r != "function", W = Array.isArray, Ct = (r) => W(r) || typeof r?.[Symbol.iterator] == "function", z = `[ 	
\f\r]`, S = /<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g, Q = /-->/g, tt = />/g, $ = RegExp(`>|${z}(?:([^\\s"'>=/]+)(${z}*=${z}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`, "g"), et = /'/g, st = /"/g, _t = /^(?:script|style|textarea|title)$/i, kt = (r) => (t, ...e) => ({ _$litType$: r, strings: t, values: e }), u = kt(1), w = /* @__PURE__ */ Symbol.for("lit-noChange"), l = /* @__PURE__ */ Symbol.for("lit-nothing"), it = /* @__PURE__ */ new WeakMap(), y = g.createTreeWalker(g, 129);
function ft(r, t) {
  if (!W(r) || !r.hasOwnProperty("raw")) throw Error("invalid template strings array");
  return X !== void 0 ? X.createHTML(t) : t;
}
const Pt = (r, t) => {
  const e = r.length - 1, s = [];
  let i, n = t === 2 ? "<svg>" : t === 3 ? "<math>" : "", o = S;
  for (let c = 0; c < e; c++) {
    const a = r[c];
    let h, p, d = -1, _ = 0;
    for (; _ < a.length && (o.lastIndex = _, p = o.exec(a), p !== null); ) _ = o.lastIndex, o === S ? p[1] === "!--" ? o = Q : p[1] !== void 0 ? o = tt : p[2] !== void 0 ? (_t.test(p[2]) && (i = RegExp("</" + p[2], "g")), o = $) : p[3] !== void 0 && (o = $) : o === $ ? p[0] === ">" ? (o = i ?? S, d = -1) : p[1] === void 0 ? d = -2 : (d = o.lastIndex - p[2].length, h = p[1], o = p[3] === void 0 ? $ : p[3] === '"' ? st : et) : o === st || o === et ? o = $ : o === Q || o === tt ? o = S : (o = $, i = void 0);
    const f = o === $ && r[c + 1].startsWith("/>") ? " " : "";
    n += o === S ? a + Et : d >= 0 ? (s.push(h), a.slice(0, d) + ut + a.slice(d) + m + f) : a + m + (d === -2 ? c : f);
  }
  return [ft(r, n + (r[e] || "<?>") + (t === 2 ? "</svg>" : t === 3 ? "</math>" : "")), s];
};
class U {
  constructor({ strings: t, _$litType$: e }, s) {
    let i;
    this.parts = [];
    let n = 0, o = 0;
    const c = t.length - 1, a = this.parts, [h, p] = Pt(t, e);
    if (this.el = U.createElement(h, s), y.currentNode = this.el.content, e === 2 || e === 3) {
      const d = this.el.content.firstChild;
      d.replaceWith(...d.childNodes);
    }
    for (; (i = y.nextNode()) !== null && a.length < c; ) {
      if (i.nodeType === 1) {
        if (i.hasAttributes()) for (const d of i.getAttributeNames()) if (d.endsWith(ut)) {
          const _ = p[o++], f = i.getAttribute(d).split(m), N = /([.?@])?(.*)/.exec(_);
          a.push({ type: 1, index: n, name: N[2], strings: f, ctor: N[1] === "." ? Mt : N[1] === "?" ? Nt : N[1] === "@" ? Tt : j }), i.removeAttribute(d);
        } else d.startsWith(m) && (a.push({ type: 6, index: n }), i.removeAttribute(d));
        if (_t.test(i.tagName)) {
          const d = i.textContent.split(m), _ = d.length - 1;
          if (_ > 0) {
            i.textContent = R ? R.emptyScript : "";
            for (let f = 0; f < _; f++) i.append(d[f], k()), y.nextNode(), a.push({ type: 2, index: ++n });
            i.append(d[_], k());
          }
        }
      } else if (i.nodeType === 8) if (i.data === pt) a.push({ type: 2, index: n });
      else {
        let d = -1;
        for (; (d = i.data.indexOf(m, d + 1)) !== -1; ) a.push({ type: 7, index: n }), d += m.length - 1;
      }
      n++;
    }
  }
  static createElement(t, e) {
    const s = g.createElement("template");
    return s.innerHTML = t, s;
  }
}
function x(r, t, e = r, s) {
  if (t === w) return t;
  let i = s !== void 0 ? e._$Co?.[s] : e._$Cl;
  const n = P(t) ? void 0 : t._$litDirective$;
  return i?.constructor !== n && (i?._$AO?.(!1), n === void 0 ? i = void 0 : (i = new n(r), i._$AT(r, e, s)), s !== void 0 ? (e._$Co ??= [])[s] = i : e._$Cl = i), i !== void 0 && (t = x(r, i._$AS(r, t.values), i, s)), t;
}
class Ut {
  constructor(t, e) {
    this._$AV = [], this._$AN = void 0, this._$AD = t, this._$AM = e;
  }
  get parentNode() {
    return this._$AM.parentNode;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  u(t) {
    const { el: { content: e }, parts: s } = this._$AD, i = (t?.creationScope ?? g).importNode(e, !0);
    y.currentNode = i;
    let n = y.nextNode(), o = 0, c = 0, a = s[0];
    for (; a !== void 0; ) {
      if (o === a.index) {
        let h;
        a.type === 2 ? h = new M(n, n.nextSibling, this, t) : a.type === 1 ? h = new a.ctor(n, a.name, a.strings, this, t) : a.type === 6 && (h = new Rt(n, this, t)), this._$AV.push(h), a = s[++c];
      }
      o !== a?.index && (n = y.nextNode(), o++);
    }
    return y.currentNode = g, i;
  }
  p(t) {
    let e = 0;
    for (const s of this._$AV) s !== void 0 && (s.strings !== void 0 ? (s._$AI(t, s, e), e += s.strings.length - 2) : s._$AI(t[e])), e++;
  }
}
class M {
  get _$AU() {
    return this._$AM?._$AU ?? this._$Cv;
  }
  constructor(t, e, s, i) {
    this.type = 2, this._$AH = l, this._$AN = void 0, this._$AA = t, this._$AB = e, this._$AM = s, this.options = i, this._$Cv = i?.isConnected ?? !0;
  }
  get parentNode() {
    let t = this._$AA.parentNode;
    const e = this._$AM;
    return e !== void 0 && t?.nodeType === 11 && (t = e.parentNode), t;
  }
  get startNode() {
    return this._$AA;
  }
  get endNode() {
    return this._$AB;
  }
  _$AI(t, e = this) {
    t = x(this, t, e), P(t) ? t === l || t == null || t === "" ? (this._$AH !== l && this._$AR(), this._$AH = l) : t !== this._$AH && t !== w && this._(t) : t._$litType$ !== void 0 ? this.$(t) : t.nodeType !== void 0 ? this.T(t) : Ct(t) ? this.k(t) : this._(t);
  }
  O(t) {
    return this._$AA.parentNode.insertBefore(t, this._$AB);
  }
  T(t) {
    this._$AH !== t && (this._$AR(), this._$AH = this.O(t));
  }
  _(t) {
    this._$AH !== l && P(this._$AH) ? this._$AA.nextSibling.data = t : this.T(g.createTextNode(t)), this._$AH = t;
  }
  $(t) {
    const { values: e, _$litType$: s } = t, i = typeof s == "number" ? this._$AC(t) : (s.el === void 0 && (s.el = U.createElement(ft(s.h, s.h[0]), this.options)), s);
    if (this._$AH?._$AD === i) this._$AH.p(e);
    else {
      const n = new Ut(i, this), o = n.u(this.options);
      n.p(e), this.T(o), this._$AH = n;
    }
  }
  _$AC(t) {
    let e = it.get(t.strings);
    return e === void 0 && it.set(t.strings, e = new U(t)), e;
  }
  k(t) {
    W(this._$AH) || (this._$AH = [], this._$AR());
    const e = this._$AH;
    let s, i = 0;
    for (const n of t) i === e.length ? e.push(s = new M(this.O(k()), this.O(k()), this, this.options)) : s = e[i], s._$AI(n), i++;
    i < e.length && (this._$AR(s && s._$AB.nextSibling, i), e.length = i);
  }
  _$AR(t = this._$AA.nextSibling, e) {
    for (this._$AP?.(!1, !0, e); t !== this._$AB; ) {
      const s = Y(t).nextSibling;
      Y(t).remove(), t = s;
    }
  }
  setConnected(t) {
    this._$AM === void 0 && (this._$Cv = t, this._$AP?.(t));
  }
}
class j {
  get tagName() {
    return this.element.tagName;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  constructor(t, e, s, i, n) {
    this.type = 1, this._$AH = l, this._$AN = void 0, this.element = t, this.name = e, this._$AM = i, this.options = n, s.length > 2 || s[0] !== "" || s[1] !== "" ? (this._$AH = Array(s.length - 1).fill(new String()), this.strings = s) : this._$AH = l;
  }
  _$AI(t, e = this, s, i) {
    const n = this.strings;
    let o = !1;
    if (n === void 0) t = x(this, t, e, 0), o = !P(t) || t !== this._$AH && t !== w, o && (this._$AH = t);
    else {
      const c = t;
      let a, h;
      for (t = n[0], a = 0; a < n.length - 1; a++) h = x(this, c[s + a], e, a), h === w && (h = this._$AH[a]), o ||= !P(h) || h !== this._$AH[a], h === l ? t = l : t !== l && (t += (h ?? "") + n[a + 1]), this._$AH[a] = h;
    }
    o && !i && this.j(t);
  }
  j(t) {
    t === l ? this.element.removeAttribute(this.name) : this.element.setAttribute(this.name, t ?? "");
  }
}
class Mt extends j {
  constructor() {
    super(...arguments), this.type = 3;
  }
  j(t) {
    this.element[this.name] = t === l ? void 0 : t;
  }
}
class Nt extends j {
  constructor() {
    super(...arguments), this.type = 4;
  }
  j(t) {
    this.element.toggleAttribute(this.name, !!t && t !== l);
  }
}
class Tt extends j {
  constructor(t, e, s, i, n) {
    super(t, e, s, i, n), this.type = 5;
  }
  _$AI(t, e = this) {
    if ((t = x(this, t, e, 0) ?? l) === w) return;
    const s = this._$AH, i = t === l && s !== l || t.capture !== s.capture || t.once !== s.once || t.passive !== s.passive, n = t !== l && (s === l || i);
    i && this.element.removeEventListener(this.name, this, s), n && this.element.addEventListener(this.name, this, t), this._$AH = t;
  }
  handleEvent(t) {
    typeof this._$AH == "function" ? this._$AH.call(this.options?.host ?? this.element, t) : this._$AH.handleEvent(t);
  }
}
class Rt {
  constructor(t, e, s) {
    this.element = t, this.type = 6, this._$AN = void 0, this._$AM = e, this.options = s;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AI(t) {
    x(this, t);
  }
}
const Ot = I.litHtmlPolyfillSupport;
Ot?.(U, M), (I.litHtmlVersions ??= []).push("3.3.3");
const Ht = (r, t, e) => {
  const s = e?.renderBefore ?? t;
  let i = s._$litPart$;
  if (i === void 0) {
    const n = e?.renderBefore ?? null;
    s._$litPart$ = i = new M(t.insertBefore(k(), n), n, void 0, e ?? {});
  }
  return i._$AI(r), i;
};
const q = globalThis;
class A extends b {
  constructor() {
    super(...arguments), this.renderOptions = { host: this }, this._$Do = void 0;
  }
  createRenderRoot() {
    const t = super.createRenderRoot();
    return this.renderOptions.renderBefore ??= t.firstChild, t;
  }
  update(t) {
    const e = this.render();
    this.hasUpdated || (this.renderOptions.isConnected = this.isConnected), super.update(t), this._$Do = Ht(e, this.renderRoot, this.renderOptions);
  }
  connectedCallback() {
    super.connectedCallback(), this._$Do?.setConnected(!0);
  }
  disconnectedCallback() {
    super.disconnectedCallback(), this._$Do?.setConnected(!1);
  }
  render() {
    return w;
  }
}
A._$litElement$ = !0, A.finalized = !0, q.litElementHydrateSupport?.({ LitElement: A });
const jt = q.litElementPolyfillSupport;
jt?.({ LitElement: A });
(q.litElementVersions ??= []).push("4.2.2");
const V = "Unassigned", C = [
  {
    key: "suspect",
    status: "suspect_battery",
    title: "Suspect battery",
    collapsible: !0,
    defaultCollapsed: !1,
    alwaysVisible: !1
  },
  {
    key: "dry",
    status: "dry",
    title: "Too dry",
    collapsible: !0,
    defaultCollapsed: !1,
    alwaysVisible: !0
  },
  {
    key: "no_data",
    status: "no_data",
    title: "No data",
    collapsible: !0,
    defaultCollapsed: !1,
    alwaysVisible: !1
  },
  {
    key: "healthy",
    status: "healthy",
    title: "Well watered",
    collapsible: !0,
    defaultCollapsed: !0,
    alwaysVisible: !1
  }
];
function F(r) {
  if (!r)
    return null;
  const t = Number(r.state);
  return Number.isFinite(t) ? t : null;
}
function O(r) {
  return r.area_name ?? V;
}
function rt(r, t) {
  return r.localeCompare(t, void 0, { sensitivity: "base" });
}
function zt(r, t, e) {
  const s = O(r), i = O(t);
  if (s !== i)
    return s === V ? 1 : i === V ? -1 : rt(s, i);
  const n = e(r), o = e(t);
  if (n === null || o === null) {
    if (n !== o)
      return n === null ? 1 : -1;
  } else if (n !== o)
    return n - o;
  return rt(r.label, t.label);
}
function Lt(r, t) {
  const e = {
    suspect: [],
    dry: [],
    no_data: [],
    healthy: []
  };
  for (const s of r) {
    const i = C.find((n) => n.status === s.status);
    i !== void 0 && e[i.key].push(s);
  }
  for (const s of C)
    e[s.key].sort((i, n) => zt(i, n, t));
  return e;
}
function Vt(r) {
  const t = [];
  for (const e of r) {
    const s = O(e), i = t[t.length - 1];
    i !== void 0 && i.area === s ? i.plants.push(e) : t.push({ area: s, plants: [e] });
  }
  return t;
}
function Bt(r) {
  if (r === null)
    return "—";
  const t = Math.round(r * 10) / 10;
  return `${Number.isInteger(t) ? t : t.toFixed(1)} %`;
}
function Dt(r) {
  if (!r)
    return "unknown";
  const t = new Date(r);
  return Number.isNaN(t.getTime()) ? "unknown" : new Intl.DateTimeFormat(void 0, {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(t);
}
function nt(r, t = "—") {
  if (!r)
    return t;
  const e = F(r);
  if (e === null)
    return t;
  const s = typeof r.attributes.unit_of_measurement == "string" ? r.attributes.unit_of_measurement : "", i = Math.round(e * 10) / 10;
  return s ? `${i} ${s}` : String(i);
}
function ot(r) {
  return F(r) === null;
}
const at = "watering-project-panel";
class It extends A {
  static {
    this.properties = { hass: { attribute: !1 } };
  }
  static {
    this.styles = ct`
    :host {
      display: block;
    }

    watering-project-card {
      display: block;
    }
  `;
  }
  render() {
    return u`<watering-project-card .hass=${this.hass}></watering-project-card>`;
  }
}
const lt = 1, v = "watering-project-card", Wt = "watering_project/subscribe", qt = "watering-project:";
let Ft = 0;
function Kt(r) {
  if (typeof r != "object" || r === null)
    return !1;
  const t = r;
  return typeof t.schema_version == "number" && Array.isArray(t.plants) && typeof t.summary == "object" && t.summary !== null && Array.isArray(t.excluded);
}
function Jt(r) {
  if (typeof r != "object" || r === null)
    return "";
  const t = r.code;
  return typeof t == "string" ? t : "";
}
function Zt(r) {
  if (r instanceof Error)
    return r.message;
  if (typeof r == "object" && r !== null) {
    const t = r.message;
    if (typeof t == "string")
      return t;
  }
  return String(r);
}
class Gt extends A {
  constructor() {
    super(...arguments), this._connection = { kind: "connecting" }, this._expanded = /* @__PURE__ */ new Set(), this._collapsed = /* @__PURE__ */ new Map(), this._memo = "", this._payloadSeq = 0, this._subscribing = !1, this._uid = `wp-${Ft += 1}`;
  }
  static {
    this.properties = {
      _payload: { state: !0 },
      _connection: { state: !0 },
      _expanded: { state: !0 },
      _collapsed: { state: !0 }
    };
  }
  setConfig(t) {
    if (!t || t.type !== `custom:${v}`)
      throw new Error(`Card type must be custom:${v}`);
    this._config = { ...t }, this._initCollapseState();
  }
  getCardSize() {
    const t = this._payload?.plants.length ?? 0;
    return 2 + C.length + Math.ceil(t / 2);
  }
  getGridOptions() {
    return { columns: 12, min_columns: 6, min_rows: 2 };
  }
  get hass() {
    return this._hassValue;
  }
  set hass(t) {
    const e = this._hassValue;
    if (this._hassValue = t, t === void 0)
      return;
    const s = this._signature(t);
    e !== void 0 && s === this._memo || (this._memo = s, this.requestUpdate(), e === void 0 && this._subscribe(t));
  }
  connectedCallback() {
    super.connectedCallback(), this._initCollapseState(), this._hassValue !== void 0 && this._unsub === void 0 && this._subscribe(this._hassValue);
  }
  disconnectedCallback() {
    this._teardown(), super.disconnectedCallback();
  }
  render() {
    const t = this._payload;
    return this._connection.kind === "not_loaded" ? this._frame(
      this._statusRow(
        "Watering Project is not loaded.",
        "The integration has no active config entry. Add it under Settings → Devices & services.",
        !0
      )
    ) : this._connection.kind === "error" ? this._frame(
      this._statusRow("Could not load plant status.", this._connection.message, !0)
    ) : t === void 0 ? this._frame(this._statusRow("Loading plant status…", "", !1)) : t.schema_version !== lt ? this._frame(
      this._statusRow(
        "Card and integration versions do not match.",
        `The card expects schema ${lt} but received ${t.schema_version}. Bump the \`?v=\` suffix of the card resource URL so the browser reloads the card.`,
        !1
      )
    ) : t.plants.length === 0 ? this._frame(u`
        <div class="status">
          <p class="status-title">No plants found.</p>
          <p class="status-detail">
            Add Zigbee moisture sensors with a moisture device class, or adjust the
            included and excluded devices in the integration options.
          </p>
        </div>
      `) : this._frame(u`
      ${this._config?.title ? u`<h2 class="card-title">${this._config.title}</h2>` : l}
      ${C.map((e) => this._renderSection(e, t))}
      ${this._renderExcluded(t)}
    `);
  }
  // -- subscription ----------------------------------------------------------
  async _subscribe(t) {
    if (this._subscribing)
      return;
    const e = t.connection;
    if (e?.subscribeMessage === void 0) {
      this._setConnection({ kind: "error", message: "Websocket connection unavailable." });
      return;
    }
    this._subscribing = !0;
    try {
      const s = await e.subscribeMessage(
        (i) => this._handleMessage(i),
        { type: Wt }
      );
      typeof s == "function" && (this._unsub = s);
    } catch (s) {
      const i = Jt(s), n = Zt(s);
      i === "not_loaded" || n.includes("not_loaded") ? this._setConnection({ kind: "not_loaded" }) : this._setConnection({ kind: "error", message: n });
    } finally {
      this._subscribing = !1;
    }
  }
  _handleMessage(t) {
    if (!Kt(t)) {
      this._setConnection({
        kind: "error",
        message: "The integration sent a payload this card cannot read."
      });
      return;
    }
    this._payload = t, this._payloadSeq += 1, this._setConnection({ kind: "ready" }), this._refreshMemo(), this.requestUpdate();
  }
  _retry() {
    this._teardown();
    const t = this._hassValue;
    this._setConnection({ kind: "connecting" }), t !== void 0 && this._subscribe(t);
  }
  _teardown() {
    const t = this._unsub;
    this._unsub = void 0, t !== void 0 && t();
  }
  _setConnection(t) {
    this._connection = t, this._refreshMemo(), this.requestUpdate();
  }
  // -- memoisation -----------------------------------------------------------
  /**
   * Cheap signature of everything the template reads from `hass`, plus the
   * payload generation. `last_reported` is deliberately absent: it moves on
   * no-op reports and would re-render the whole card for nothing.
   */
  _signature(t) {
    const e = [String(this._payloadSeq), this._connection.kind];
    for (const s of this._payload?.plants ?? [])
      e.push(this._entitySignature(t.states[s.moisture_entity_id])), s.battery_entity_id !== null && e.push(this._entitySignature(t.states[s.battery_entity_id])), s.temperature_entity_id !== null && e.push(this._entitySignature(t.states[s.temperature_entity_id]));
    return e.join("|");
  }
  _entitySignature(t) {
    if (t === void 0)
      return "-";
    const e = t.attributes.unit_of_measurement;
    return `${t.state}/${typeof e == "string" ? e : ""}`;
  }
  _refreshMemo() {
    this._hassValue !== void 0 && (this._memo = this._signature(this._hassValue));
  }
  // -- collapse state --------------------------------------------------------
  _storageKey() {
    const t = this._config?.id ?? (this._config === void 0 ? "panel" : void 0);
    return t === void 0 || t === "" ? void 0 : `${qt}${t}:collapsed`;
  }
  _initCollapseState() {
    const t = new Map(
      C.map((s) => [s.key, s.defaultCollapsed])
    ), e = this._storageKey();
    if (e !== void 0)
      try {
        const s = window.localStorage.getItem(e);
        if (s !== null) {
          const i = JSON.parse(s);
          if (typeof i == "object" && i !== null)
            for (const [n, o] of Object.entries(i))
              t.has(n) && t.set(n, o === !0);
        }
      } catch {
      }
    this._collapsed = t;
  }
  _persistCollapse() {
    const t = this._storageKey();
    if (t !== void 0)
      try {
        window.localStorage.setItem(t, JSON.stringify(Object.fromEntries(this._collapsed)));
      } catch {
      }
  }
  _toggleSection(t) {
    t.collapsible && (this._collapsed.set(t.key, !this._collapsed.get(t.key)), this._persistCollapse(), this.requestUpdate());
  }
  _togglePlant(t) {
    this._expanded.has(t.plant_id) ? this._expanded.delete(t.plant_id) : this._expanded.add(t.plant_id), this.requestUpdate();
  }
  // -- rendering -------------------------------------------------------------
  _frame(t) {
    return u`<ha-card><div class="content">${t}</div></ha-card>`;
  }
  _statusRow(t, e, s) {
    return u`
      <div class="status">
        <p class="status-title">${t}</p>
        ${e ? u`<p class="status-detail">${e}</p>` : l}
        ${s ? u`<button class="retry" @click=${() => this._retry()}>Retry</button>` : l}
      </div>
    `;
  }
  _liveMoisture(t) {
    const e = this._hassValue?.states[t.moisture_entity_id];
    return F(e) ?? t.moisture;
  }
  _renderSection(t, e) {
    const s = Lt(e.plants, (o) => this._liveMoisture(o))[t.key];
    if (s.length === 0 && !t.alwaysVisible)
      return l;
    const i = this._collapsed.get(t.key) === !0, n = `${this._uid}-${t.key}`;
    return u`
      <section class="section section-${t.key}" data-section=${t.key}>
        <button
          class="section-header"
          aria-expanded=${i ? "false" : "true"}
          aria-controls=${n}
          @click=${() => this._toggleSection(t)}
        >
          <span class="section-title">${t.title}</span>
          <span class="count">${s.length}</span>
          <span class="chevron" aria-hidden="true">${i ? "▸" : "▾"}</span>
        </button>
        <div class="section-body" id=${n} ?hidden=${i}>
          ${s.length === 0 ? u`<p class="section-empty">No plants.</p>` : Vt(s).map(
      (o) => u`
                  <div class="room">
                    <h3 class="room-title">${o.area}</h3>
                    ${o.plants.map((c) => this._renderPlant(c))}
                  </div>
                `
    )}
        </div>
      </section>
    `;
  }
  _renderPlant(t) {
    const e = this._expanded.has(t.plant_id), s = this._hassValue?.states ?? {}, i = t.battery_entity_id === null ? void 0 : s[t.battery_entity_id], n = t.temperature_entity_id === null ? void 0 : s[t.temperature_entity_id], o = t.temperature_entity_id !== null && ot(n), c = t.battery_entity_id !== null && (t.battery.never_reported || ot(i)), a = this._liveMoisture(t);
    return u`
      <div class="plant" data-plant-id=${t.plant_id}>
        <button
          class="plant-row"
          aria-expanded=${e ? "true" : "false"}
          data-status=${t.status}
          @click=${() => this._togglePlant(t)}
        >
          <span class="dot" aria-hidden="true"></span>
          <span class="plant-name">${t.label}</span>
          ${o ? u`<span class="badge" title="Temperature unknown">temp?</span>` : l}
          ${c ? u`<span class="badge" title="Battery value unknown">batt?</span>` : l}
          <span class="moisture">${Bt(a)}</span>
        </button>
        ${e ? u`
              <dl class="details">
                <dt>Room</dt>
                <dd>${O(t)}</dd>
                <dt>Temperature</dt>
                <dd>${nt(n)}</dd>
                <dt>Battery</dt>
                <dd>${nt(i)}</dd>
                <dt>Last reported</dt>
                <dd>
                  ${Dt(
      s[t.moisture_entity_id]?.last_reported ?? s[t.moisture_entity_id]?.last_updated
    )}
                </dd>
                ${t.zero_days !== null ? u`<dt>Battery flat for</dt>
                      <dd>${t.zero_days} ${t.zero_days === 1 ? "day" : "days"}</dd>` : l}
              </dl>
            ` : l}
      </div>
    `;
  }
  _renderExcluded(t) {
    return t.excluded.length === 0 ? l : u`
      <details class="excluded">
        <summary>${t.excluded.length} device(s) excluded</summary>
        <ul>
          ${t.excluded.map(
      (e) => u`<li>${e.label} <span class="reason">${e.reason}</span></li>`
    )}
        </ul>
      </details>
    `;
  }
  static {
    this.styles = ct`
    :host {
      display: block;
    }

    .content {
      padding: 12px 16px 16px;
    }

    .card-title {
      margin: 4px 0 12px;
      font-size: 1.5rem;
      font-weight: 400;
      color: var(--primary-text-color);
    }

    .section + .section {
      border-top: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
    }

    .section-header {
      display: flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      padding: 10px 0;
      background: none;
      border: none;
      color: var(--primary-text-color);
      font: inherit;
      font-weight: 500;
      text-align: left;
      cursor: pointer;
    }

    .section-header:focus-visible,
    .plant-row:focus-visible,
    .retry:focus-visible {
      outline: 2px solid var(--primary-color, #03a9f4);
      outline-offset: 2px;
    }

    .count {
      padding: 1px 8px;
      border-radius: 10px;
      background: var(--secondary-background-color, rgba(0, 0, 0, 0.08));
      color: var(--secondary-text-color);
      font-size: 0.8rem;
    }

    .chevron {
      margin-left: auto;
      color: var(--secondary-text-color);
    }

    .section-suspect .section-title {
      color: var(--warning-color, #ff9800);
    }

    .section-dry .section-title {
      color: var(--error-color, #db4437);
    }

    .room-title {
      margin: 8px 0 2px;
      font-size: 0.8rem;
      font-weight: 500;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--secondary-text-color);
    }

    .plant-row {
      display: flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      padding: 8px 0;
      background: none;
      border: none;
      color: var(--primary-text-color);
      font: inherit;
      text-align: left;
      cursor: pointer;
    }

    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--success-color, #4caf50);
      flex: none;
    }

    .plant-row[data-status="dry"] .dot {
      background: var(--error-color, #db4437);
    }

    .plant-row[data-status="suspect_battery"] .dot {
      background: var(--warning-color, #ff9800);
    }

    .plant-row[data-status="no_data"] .dot {
      background: var(--disabled-text-color, #9e9e9e);
    }

    .plant-name {
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .moisture {
      font-variant-numeric: tabular-nums;
      color: var(--secondary-text-color);
    }

    .badge {
      padding: 0 6px;
      border-radius: 8px;
      border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.2));
      color: var(--secondary-text-color);
      font-size: 0.7rem;
      line-height: 1.5;
      white-space: nowrap;
    }

    .details {
      display: grid;
      grid-template-columns: max-content 1fr;
      gap: 2px 16px;
      margin: 0 0 8px 16px;
      font-size: 0.85rem;
    }

    .details dt {
      color: var(--secondary-text-color);
    }

    .details dd {
      margin: 0;
    }

    .section-empty,
    .status-detail {
      margin: 4px 0 8px;
      color: var(--secondary-text-color);
      font-size: 0.9rem;
    }

    .status-title {
      margin: 8px 0 4px;
      font-weight: 500;
    }

    .retry {
      margin-top: 4px;
      padding: 6px 14px;
      border-radius: 4px;
      border: 1px solid var(--primary-color, #03a9f4);
      background: none;
      color: var(--primary-color, #03a9f4);
      font: inherit;
      cursor: pointer;
    }

    .excluded {
      margin-top: 12px;
      border-top: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
      padding-top: 8px;
      color: var(--secondary-text-color);
      font-size: 0.85rem;
    }

    .excluded summary {
      cursor: pointer;
    }

    .excluded ul {
      margin: 4px 0 0;
      padding-left: 20px;
    }

    .reason {
      opacity: 0.75;
    }

    [hidden] {
      display: none !important;
    }
  `;
  }
}
typeof window < "u" && typeof customElements < "u" && (customElements.get(v) || customElements.define(v, Gt), customElements.get(at) || customElements.define(at, It), window.customCards = window.customCards ?? [], window.customCards.some((r) => r.type === v) || window.customCards.push({
  type: v,
  name: "Watering Project",
  description: "Plant moisture overview grouped by room, ordered by urgency.",
  preview: !1,
  documentationURL: "https://github.com/Mixermachine/WateringProject#readme"
}));
export {
  v as CARD_TYPE,
  Wt as SUBSCRIBE_TYPE,
  Gt as WateringProjectCard
};
