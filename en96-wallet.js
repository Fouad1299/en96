
/*
 EN96 ICE BEAR KINGDOM
 Stellar Wallet Integration
 Reown + LOBSTR preparation

 No secret keys.
 No automatic payments.
 No mining boosts until verification.
*/

(function () {
  "use strict";

  const CONFIG = Object.freeze({
    projectName: "EN96 Ice Bear Kingdom",

    projectId:
      "3e9fa0461e993b4dbc10fb444a3ca46f",

    network: "stellar:pubnet",

    stellarIssuer:
      "GCUGIICUGBFC3KBPIFYAMPNA7OVJHGY277TNYTZUSG7EVVUCVACH3OGB",

    assetCode: "EN96",

    apiBase: "https://en96.onrender.com",

    website:
      "https://fouad1299.github.io/en96/en96-royal.html"
  });

  const state = {
    address: null,
    verified: false,
    connected: false
  };

  function telegramData() {
    const telegram = window.Telegram?.WebApp;
    return telegram?.initData || "";
  }

  function validStellarAddress(address) {
    return (
      typeof address === "string" &&
      /^G[A-Z2-7]{55}$/.test(address)
    );
  }

  async function apiRequest(path) {
    const initData = telegramData();

    if (!initData) {
      throw new Error(
        "افتح EN96 من داخل Telegram."
      );
    }

    const response = await fetch(
      CONFIG.apiBase + path,
      {
        method: "GET",
        headers: {
          Authorization: "tma " + initData
        },
        cache: "no-store"
      }
    );

    const data = await response.json();

    if (!response.ok) {
      throw new Error(
        data.error || "تعذر الاتصال بالخادم"
      );
    }

    return data;
  }

  // Reads the stored public address.
  // This is NOT proof of wallet ownership.
  async function loadWallet() {
    const data = await apiRequest("/api/me");

    const address =
      data.stellar_public_address || "";

    state.address = validStellarAddress(address)
      ? address
      : null;

    return {
      address: state.address,
      available: data.available,
      reserved: data.reserved,
      verified: false
    };
  }

  // WalletConnect and signature verification
  // will be attached in the next integration step.
  async function connectLOBSTR() {
    throw new Error(
      "ربط LOBSTR لم يُفعّل بعد. " +
      "يجب تركيب WalletConnect " +
      "والتحقق من التوقيع في الخادم."
    );
  }

  function getState() {
    return {
      address: state.address,
      connected: state.connected,
      verified: state.verified,
      network: CONFIG.network
    };
  }

  window.EN96Wallet = Object.freeze({
    config: CONFIG,
    loadWallet,
    connectLOBSTR,
    getState,
    validStellarAddress
  });

  console.info(
    "EN96 Wallet configuration loaded"
  );
})();
