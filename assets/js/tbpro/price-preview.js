/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

(function () {
  'use strict';

  function isNonEmptyString(value) {
    return typeof value === 'string' && value !== '';
  }

  function isDataObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }

  function onlyElement(nodes) {
    if (nodes.length !== 1) {
      return null;
    }
    return nodes[0];
  }

  function validateRoot(root) {
    const dataNode = onlyElement(root.querySelectorAll('script.subscription-price-data'));
    const control = onlyElement(root.querySelectorAll('.subscription-price-control'));
    if (!dataNode || !control || dataNode.getAttribute('type') !== 'application/json') {
      return null;
    }
    if (!control.hasAttribute('hidden')) {
      return null;
    }

    const select = onlyElement(control.querySelectorAll('select'));
    const priceNode = onlyElement(root.querySelectorAll('.subscription-price'));
    if (!select || !priceNode || control.contains(priceNode)) {
      return null;
    }

    let data;
    try {
      data = JSON.parse(dataNode.textContent);
    } catch (error) {
      return null;
    }
    if (!isDataObject(data) || !isNonEmptyString(data.defaultCountry) || !Array.isArray(data.countries)) {
      return null;
    }

    const prices = new Map();
    for (const country of data.countries) {
      if (!isDataObject(country) || !isNonEmptyString(country.code) || !isNonEmptyString(country.price)) {
        return null;
      }
      if (prices.has(country.code)) {
        return null;
      }
      prices.set(country.code, country.price);
    }

    const optionValues = new Set();
    let selectedValue = null;
    for (const option of select.querySelectorAll('option')) {
      const value = option.getAttribute('value');
      if (!isNonEmptyString(value) || optionValues.has(value)) {
        return null;
      }
      optionValues.add(value);
      if (option.hasAttribute('selected')) {
        if (selectedValue !== null) {
          return null;
        }
        selectedValue = value;
      }
    }

    if (optionValues.size !== prices.size || !prices.has(data.defaultCountry)) {
      return null;
    }
    for (const code of prices.keys()) {
      if (!optionValues.has(code)) {
        return null;
      }
    }
    if (selectedValue !== data.defaultCountry) {
      return null;
    }
    if (priceNode.textContent !== prices.get(data.defaultCountry)) {
      return null;
    }

    return {
      control: control,
      select: select,
      priceNode: priceNode,
      prices: prices,
    };
  }

  function initRoot(root) {
    const component = validateRoot(root);
    if (!component) {
      return;
    }

    function onCountryChange() {
      const nextPrice = component.prices.get(component.select.value);
      if (nextPrice === undefined) {
        return;
      }
      component.priceNode.textContent = nextPrice;
    }

    component.select.addEventListener('change', onCountryChange);
    component.control.removeAttribute('hidden');
  }

  const roots = document.querySelectorAll('.subscription-price-preview');
  Array.prototype.forEach.call(roots, function (root) {
    try {
      initRoot(root);
    } catch (error) {
      // Leave progressive enhancement disabled for this component.
    }
  });
}());
