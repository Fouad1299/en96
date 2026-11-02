
/*
 EN96 Ice Bear Kingdom
 Royal Wallet Selector

 Stellar Mainnet
 No private keys
 No transactions
 No unverified mining boosts
*/

(function () {
  "use strict";

  const CONFIG = Object.freeze({
    projectName: "EN96 Ice Bear Kingdom",
    projectId: "3e9fa0461e993b4dbc10fb444a3ca46f",
    network: "stellar:pubnet",
    assetCode: "EN96",
    issuer:
      "GCUGIICUGBFC3KBPIFYAMPNA7OVJHGY277TNYTZUSG7EVVUCVACH3OGB",
    apiBase: "https://en96.onrender.com"
  });

  let selected = null;

  function validStellarAddress(address) {
    return (
      typeof address === "string" &&
      /^G[A-Z2-7]{55}$/.test(address.trim())
    );
  }

  async function loadWallet() {
    const initData =
      window.Telegram?.WebApp?.initData || "";

    if (!initData) {
      throw new Error(
        "افتح التطبيق من داخل Telegram."
      );
    }

    const response = await fetch(
      CONFIG.apiBase + "/api/me",
      {
        headers: {
          Authorization: "tma " + initData
        },
        cache: "no-store"
      }
    );

    const data = await response.json();

    if (!response.ok) {
      throw new Error(
        data.error || "تعذر تحميل المحفظة."
      );
    }

    return {
      address: data.stellar_public_address || "",
      available: data.available,
      reserved: data.reserved,
      verified: false
    };
  }

  function installStyles() {
    const style = document.createElement("style");

    style.textContent = `
      .en96-connect-button {
        display:block;
        width:100%;
        margin:14px 0;
        padding:16px;
        border:1px solid #fff0a4;
        border-radius:17px;
        color:#512300;
        font-weight:900;
        font-size:17px;
        background:linear-gradient(
          135deg,#fff19e,#ffca36,#f49a13
        );
        box-shadow:0 4px 15px #ffb52b55;
      }

      .en96-wallet-overlay {
        position:fixed;
        inset:0;
        z-index:9999;
        background:rgba(0,0,0,.78);
        display:flex;
        align-items:flex-end;
        justify-content:center;
        padding:12px;
      }

      .en96-wallet-modal {
        width:100%;
        max-width:500px;
        max-height:85dvh;
        overflow-y:auto;
        background:linear-gradient(
          145deg,#4e1a11,#220b0c
        );
        border:2px solid #efbd58;
        border-radius:24px;
        padding:20px 16px;
        color:white;
        box-shadow:0 0 35px #ffb31b55;
        font-family:Arial,Tahoma,sans-serif;
        direction:rtl;
      }

      .en96-wallet-modal h2 {
        margin:6px 0 9px;
        font-size:23px;
        color:#ffe18e;
        text-align:center;
      }

      .en96-wallet-modal p {
        color:#f4d8c8;
        font-size:12px;
        line-height:1.8;
        text-align:center;
      }

      .en96-wallet-choice {
        display:flex;
        align-items:center;
        width:100%;
        gap:13px;
        margin-top:10px;
        padding:14px;
        background:#32110f;
        border:1px solid #b78a4b;
        border-radius:15px;
        color:white;
        text-align:right;
        cursor:pointer;
      }

      .en96-wallet-choice:disabled {
        opacity:.55;
        cursor:not-allowed;
      }

      .en96-wallet-choice .symbol {
        display:grid;
        place-items:center;
        width:46px;
        height:46px;
        flex-shrink:0;
        border-radius:13px;
        background:#6e4218;
        font-size:25px;
      }

      .en96-wallet-choice strong {
        display:block;
        font-size:15px;
      }

      .en96-wallet-choice small {
        display:block;
        margin-top:5px;
        color:#eac6ad;
        font-size:11px;
      }

      .en96-wallet-close {
        width:100%;
        margin-top:17px;
        background:#532018;
        border:1px solid #b98b55;
        color:#ffe4a8;
        border-radius:13px;
        padding:12px;
        font-weight:bold;
      }

      .en96-wallet-selection {
        padding:12px;
        margin:12px 0;
        border:1px solid #a87d46;
        border-radius:12px;
        background:#2d110d;
        font-size:12px;
        color:#ffe1b6;
        line-height:1.8;
      }
    `;

    document.head.appendChild(style);
  }

  function choice(symbol, name, description, enabled) {
    const button = document.createElement("button");

    button.type = "button";
    button.className = "en96-wallet-choice";
    button.disabled = !enabled;

    const icon = document.createElement("span");
    icon.className = "symbol";
    icon.textContent = symbol;

    const text = document.createElement("span");

    const title = document.createElement("strong");
    title.textContent = name;

    const detail = document.createElement("small");
    detail.textContent = description;

    text.append(title, detail);
    button.append(icon, text);

    if (enabled) {
      button.addEventListener("click", function () {
        selected = name;
        closeModal();

        const status =
          document.getElementById("en96WalletSelection");

        if (status) {
          status.textContent =
            "✅ اخترت " + name +
            ". لم يُنشأ اتصال بالمحفظة بعد. " +
            "يجب إكمال WalletConnect " +
            "وتوقيع إثبات الملكية قبل التفعيل.";
        }
      });
    }

    return button;
  }

  function closeModal() {
    const overlay =
      document.getElementById("en96WalletOverlay");

    if (overlay) {
      overlay.remove();
    }
  }

  function openModal() {
    closeModal();

    const overlay = document.createElement("div");
    overlay.id = "en96WalletOverlay";
    overlay.className = "en96-wallet-overlay";

    const modal = document.createElement("div");
    modal.className = "en96-wallet-modal";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute(
      "aria-label",
      "اختيار محفظة EN96"
    );

    const heading = document.createElement("h2");
    heading.textContent = "👑 Connect Wallet";

    const description = document.createElement("p");
    description.textContent =
      "اختر محفظتك. EN96 أصل على Stellar Mainnet. " +
      "لا تشارك مفاتيحك السرية أبدًا.";

    modal.append(heading, description);

    modal.appendChild(
      choice(
        "🪙",
        "LOBSTR Wallet",
        "Stellar — المحفظة الأساسية",
        true
      )
    );

    modal.appendChild(
      choice(
        "✦",
        "StellarTerm",
        "Stellar — خيار بديل",
        true
      )
    );

    modal.appendChild(
      choice(
        "🟡",
        "Binance Web3 Wallet",
        "غير مفعّل لعملة EN96 على Stellar",
        false
      )
    );

    modal.appendChild(
      choice(
        "💎",
        "Telegram Wallet",
        "غير مفعّل لعملة EN96 على Stellar",
        false
      )
    );

    const close = document.createElement("button");
    close.type = "button";
    close.className = "en96-wallet-close";
    close.textContent = "✕ إغلاق";
    close.addEventListener("click", closeModal);

    modal.appendChild(close);
    overlay.appendChild(modal);

    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) {
        closeModal();
      }
    });

    document.body.appendChild(overlay);
  }

  function installWalletButton() {
    const wallet = document.getElementById("wallet");

    if (!wallet) {
      return;
    }

    if (document.getElementById("en96ConnectWallet")) {
      return;
    }

    const button = document.createElement("button");
    button.id = "en96ConnectWallet";
    button.type = "button";
    button.className = "en96-connect-button";
    button.textContent = "👑 Connect Wallet";

    button.addEventListener("click", openModal);

    const status = document.createElement("div");
    status.id = "en96WalletSelection";
    status.className = "en96-wallet-selection";
    status.textContent =
      "🔒 لا توجد محفظة موثّقة بالتوقيع حتى الآن.";

    const title = wallet.querySelector(".page-title");

    if (title) {
      title.insertAdjacentElement("afterend", button);
    } else {
      wallet.prepend(button);
    }

    button.insertAdjacentElement("afterend", status);
  }

  function getState() {
    return {
      selectedWallet: selected,
      verified: false,
      connected: false,
      network: CONFIG.network
    };
  }

  window.EN96Wallet = Object.freeze({
    config: CONFIG,
    loadWallet,
    openModal,
    getState,
    validStellarAddress
  });

  function initialize() {
    installStyles();
    installWalletButton();
  }

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      initialize,
      { once: true }
    );
  } else {
    initialize();
  }
})();
