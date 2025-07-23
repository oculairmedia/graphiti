/**
 * @license
 * Copyright 2020 Google Inc.
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
 */
var E={UNKNOWN:"Unknown",BACKSPACE:"Backspace",ENTER:"Enter",SPACEBAR:"Spacebar",PAGE_UP:"PageUp",PAGE_DOWN:"PageDown",END:"End",HOME:"Home",ARROW_LEFT:"ArrowLeft",ARROW_UP:"ArrowUp",ARROW_RIGHT:"ArrowRight",ARROW_DOWN:"ArrowDown",DELETE:"Delete",ESCAPE:"Escape",TAB:"Tab"},d=new Set;d.add(E.BACKSPACE),d.add(E.ENTER),d.add(E.SPACEBAR),d.add(E.PAGE_UP),d.add(E.PAGE_DOWN),d.add(E.END),d.add(E.HOME),d.add(E.ARROW_LEFT),d.add(E.ARROW_UP),d.add(E.ARROW_RIGHT),d.add(E.ARROW_DOWN),d.add(E.DELETE),d.add(E.ESCAPE),d.add(E.TAB);var A=8,R=13,a=32,e=33,O=34,P=35,W=36,t=37,_=38,N=39,r=40,D=46,T=27,s=9,n=new Map;n.set(A,E.BACKSPACE),n.set(R,E.ENTER),n.set(a,E.SPACEBAR),n.set(e,E.PAGE_UP),n.set(O,E.PAGE_DOWN),n.set(P,E.END),n.set(W,E.HOME),n.set(t,E.ARROW_LEFT),n.set(_,E.ARROW_UP),n.set(N,E.ARROW_RIGHT),n.set(r,E.ARROW_DOWN),n.set(D,E.DELETE),n.set(T,E.ESCAPE),n.set(s,E.TAB);var C=new Set;function U(A){var R=A.key;if(d.has(R))return R;var a=n.get(A.keyCode);return a||E.UNKNOWN}C.add(E.PAGE_UP),C.add(E.PAGE_DOWN),C.add(E.END),C.add(E.HOME),C.add(E.ARROW_LEFT),C.add(E.ARROW_UP),C.add(E.ARROW_RIGHT),C.add(E.ARROW_DOWN);export{E as KEY,U as normalizeKey};
//# sourceMappingURL=keyboard.js.map
