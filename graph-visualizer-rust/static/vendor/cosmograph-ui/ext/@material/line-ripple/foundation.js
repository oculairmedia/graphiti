import{__extends as t,__assign as e}from"../../../_virtual/_tslib.js";import{MDCFoundation as n}from"../base/foundation.js";import{cssClasses as r}from"./constants.js";
/**
 * @license
 * Copyright 2018 Google Inc.
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */var a=function(n){function a(t){var r=n.call(this,e(e({},a.defaultAdapter),t))||this;return r.transitionEndHandler=function(t){r.handleTransitionEnd(t)},r}return t(a,n),Object.defineProperty(a,"cssClasses",{get:function(){return r},enumerable:!1,configurable:!0}),Object.defineProperty(a,"defaultAdapter",{get:function(){return{addClass:function(){},removeClass:function(){},hasClass:function(){return!1},setStyle:function(){},registerEventHandler:function(){},deregisterEventHandler:function(){}}},enumerable:!1,configurable:!0}),a.prototype.init=function(){this.adapter.registerEventHandler("transitionend",this.transitionEndHandler)},a.prototype.destroy=function(){this.adapter.deregisterEventHandler("transitionend",this.transitionEndHandler)},a.prototype.activate=function(){this.adapter.removeClass(r.LINE_RIPPLE_DEACTIVATING),this.adapter.addClass(r.LINE_RIPPLE_ACTIVE)},a.prototype.setRippleCenter=function(t){this.adapter.setStyle("transform-origin",t+"px center")},a.prototype.deactivate=function(){this.adapter.addClass(r.LINE_RIPPLE_DEACTIVATING)},a.prototype.handleTransitionEnd=function(t){var e=this.adapter.hasClass(r.LINE_RIPPLE_DEACTIVATING);"opacity"===t.propertyName&&e&&(this.adapter.removeClass(r.LINE_RIPPLE_ACTIVE),this.adapter.removeClass(r.LINE_RIPPLE_DEACTIVATING))},a}(n);export{a as MDCLineRippleFoundation,a as default};
//# sourceMappingURL=foundation.js.map
