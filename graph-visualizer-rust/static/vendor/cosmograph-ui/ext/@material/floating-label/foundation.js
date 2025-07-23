import{__extends as t,__assign as e}from"../../../_virtual/_tslib.js";import{MDCFoundation as a}from"../base/foundation.js";import{cssClasses as n}from"./constants.js";
/**
 * @license
 * Copyright 2016 Google Inc.
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
 */var r=function(a){function r(t){var n=a.call(this,e(e({},r.defaultAdapter),t))||this;return n.shakeAnimationEndHandler=function(){n.handleShakeAnimationEnd()},n}return t(r,a),Object.defineProperty(r,"cssClasses",{get:function(){return n},enumerable:!1,configurable:!0}),Object.defineProperty(r,"defaultAdapter",{get:function(){return{addClass:function(){},removeClass:function(){},getWidth:function(){return 0},registerInteractionHandler:function(){},deregisterInteractionHandler:function(){}}},enumerable:!1,configurable:!0}),r.prototype.init=function(){this.adapter.registerInteractionHandler("animationend",this.shakeAnimationEndHandler)},r.prototype.destroy=function(){this.adapter.deregisterInteractionHandler("animationend",this.shakeAnimationEndHandler)},r.prototype.getWidth=function(){return this.adapter.getWidth()},r.prototype.shake=function(t){var e=r.cssClasses.LABEL_SHAKE;t?this.adapter.addClass(e):this.adapter.removeClass(e)},r.prototype.float=function(t){var e=r.cssClasses,a=e.LABEL_FLOAT_ABOVE,n=e.LABEL_SHAKE;t?this.adapter.addClass(a):(this.adapter.removeClass(a),this.adapter.removeClass(n))},r.prototype.setRequired=function(t){var e=r.cssClasses.LABEL_REQUIRED;t?this.adapter.addClass(e):this.adapter.removeClass(e)},r.prototype.handleShakeAnimationEnd=function(){var t=r.cssClasses.LABEL_SHAKE;this.adapter.removeClass(t)},r}(a);export{r as MDCFloatingLabelFoundation,r as default};
//# sourceMappingURL=foundation.js.map
