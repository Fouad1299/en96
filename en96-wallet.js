
/*
 EN96 Ice Bear Kingdom
 Royal Stellar Wallet - Simple Version

 Mainnet
 Public G addresses only
 No secret keys or seed phrases
 No automatic payments
*/

(function () {
  "use strict";

  const CONFIG = Object.freeze({
    assetCode: "EN96",
    issuer:
      "GCUGIICUGBFC3KBPIFYAMPNA7OVJHGY277TNYTZUSG7EVVUCVACH3OGB",
    horizon: "https://horizon.stellar.org",
    lobstr: "https://lobstr.co/",
    network: "Stellar Mainnet"
  });

  const validAddress = value =>
    typeof value === "string" &&
    /^G[A-Z2-7]{55}$/.test(
      value.trim().toUpperCase()
    );

  function element(id) {
    return document.getElementById(id);
  }

  function setStatus(message) {
    const node = element("stellarStatus");
    if (node) {
      node.textContent = message;
    }
  }

  function openExternal(url) {
    const tg = window.Telegram?.WebApp;

    if (tg?.openLink) {
      tg.openLink(url);
    } else {
      window.open(
        url,
        "_blank",
        "noopener,noreferrer"
      );
    }
  }

  function addStyles() {
    if (element("en96SimpleWalletStyle")) return;

    const css = document.createElement("style");
    css.id = "en96SimpleWalletStyle";

    css.textContent = `
      .en96-simple-card {
        padding: 18px;
        margin-top: 14px;
        border: 1px solid #e7bd69;
        border-radius: 18px;
        background: #29120f;
        color: #ffe9c4;
      }

      .en96-simple-card h3 {
        margin: 0 0 12px;
        font-size: 19px;
        color: #ffe39c;
      }

      .en96-simple-card p {
        font-size: 13px;
        line-height: 1.9;
      }

      .en96-simple-button {
        display: block;
        width: 100%;
        margin: 10px 0;
        padding: 15px 12px;
        border: 1px solid #ffe49a;
        border-radius: 13px;
        background: linear-gradient(
          135deg,
          #fff09b,
          #ffbf38
        );
        color: #3c1e05;
        font-size: 15px;
        font-weight: bold;
        cursor: pointer;
      }

      .en96-simple-button.secondary {
        background: #4a2418;
        color: #ffe5ab;
        border-color: #bd8a52;
      }

      .en96-simple-input {
        width: 100%;
        padding: 15px;
        border: 1px solid #dfbd7e;
        border-radius: 12px;
        color: #fff;
        background: #160b0b;
        direction: ltr;
        text-align: left;
        font-size: 14px;
      }

      .en96-simple-status {
        padding: 13px;
        margin-top: 12px;
        border: 1px solid #a47c4a;
        border-radius: 12px;
        background: #160b0b;
        color: #ffe9ca;
        font-size: 12px;
        line-height: 1.9;
        white-space: pre-line;
        overflow-wrap: anywhere;
      }

      .en96-simple-address {
        padding: 12px;
        direction: ltr;
        text-align: left;
        overflow-wrap: anywhere;
        font-size: 12px;
        color: #ffe49b;
      }
    `;

    document.head.appendChild(css);
  }

  function card(title, description) {
    const box = document.createElement("section");
    box.className = "en96-simple-card";

    const heading = document.createElement("h3");
    heading.textContent = title;

    const para = document.createElement("p");
    para.textContent = description;

    box.append(heading, para);
    return box;
  }

  function button(label, action, secondary = false) {
    const btn = document.createElement("button");
    btn.type = "button";

    btn.className =
      "en96-simple-button" +
      (secondary ? " secondary" : "");

    btn.textContent = label;
    btn.addEventListener("click", action);

    return btn;
  }

  function currentAddress() {
    return (
      element("stellarAddress")?.value || ""
    ).trim().toUpperCase();
  }

  function createWallet() {
    openExternal(CONFIG.lobstr);
    setStatus(
      "🪙 تم فتح موقع LOBSTR.\n" +
      "أنشئ محفظتك داخل التطبيق الرسمي.\n" +
      "ثم افتح Receive وانسخ عنوان G العام.\n" +
      "لا تشارك المفتاح السري مع أحد."
    );
  }

  async function checkTrustline() {
    const address = currentAddress();

    if (!validAddress(address)) {
      setStatus(
        "⚠️ أدخل عنوان Stellar العام أولًا.\n" +
        "يجب أن يبدأ بحرف G ويتكون من 56 حرفًا."
      );
      return;
    }

    setStatus(
      "🔄 جارٍ فحص الحساب على شبكة Stellar..."
    );

    try {
      const response = await fetch(
        CONFIG.horizon +
        "/accounts/" +
        encodeURIComponent(address),
        {
          method: "GET",
          cache: "no-store"
        }
      );

      if (response.status === 404) {
        setStatus(
          "⚠️ هذا الحساب غير موجود أو غير مفعل " +
          "على Stellar Mainnet.\n" +
          "تحقق من العنوان وتفعيل حسابك بـ XLM."
        );
        return;
      }

      if (!response.ok) {
        throw new Error(
          "تعذر الوصول إلى شبكة Stellar."
        );
      }

      const account = await response.json();

      const asset = (account.balances || []).find(
        item =>
          item.asset_type !== "native" &&
          item.asset_code === CONFIG.assetCode &&
          item.asset_issuer === CONFIG.issuer
      );

      if (asset) {
        setStatus(
          "✅ خط الثقة EN96 موجود على Stellar!\n" +
          "💎 رصيد المحفظة على الشبكة: " +
          asset.balance + " EN96\n" +
          "✅ العملة والمُصدر متطابقان.\n" +
          "🔒 هذا فحص عام، وليس إثباتًا " +
          "لملكية العنوان."
        );
      } else {
        setStatus(
          "⚠️ لا يوجد خط ثقة EN96 لهذا الحساب.\n" +
          "افتح LOBSTR، ثم Add Asset.\n" +
          "ابحث عن EN96 بالمُصدر الصحيح.\n" +
          "وافق على إنشاء خط الثقة داخل LOBSTR."
        );
      }
    } catch (error) {
      setStatus(
        "⚠️ تعذر التحقق الآن.\n" +
        (error.message || "خطأ في الاتصال.")
      );
    }
  }

  async function saveAddress() {
    const address = currentAddress();

    if (!validAddress(address)) {
      setStatus(
        "⚠️ عنوان G غير صالح."
      );
      return;
    }

    if (
      typeof window.saveRoyalStellarAddress !==
      "function"
    ) {
      setStatus(
        "⚠️ وظيفة حفظ العنوان غير متاحة."
      );
      return;
    }

    await window.saveRoyalStellarAddress();
  }

  function copyIssuer() {
    const issuer = CONFIG.issuer;

    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(issuer)
        .then(() => {
          setStatus(
            "✅ تم نسخ عنوان مُصدر EN96.\n" +
            "افتح LOBSTR وابحث عن الأصل EN96 " +
            "باستخدام المُصدر المنسوخ."
          );
        })
        .catch(() => {
          setStatus("المُصدر:\n" + issuer);
        });
    } else {
      setStatus("المُصدر:\n" + issuer);
    }
  }

  function initialize() {
    const wallet = element("wallet");

    if (!wallet || element("en96WalletControls")) {
      return;
    }

    addStyles();

    // Preserve the real Supabase balance area.
    // Remove old, duplicated wallet panels only.
    wallet.querySelectorAll(".card").forEach(
      old => old.remove()
    );

    const oldConnect = element("en96ConnectWallet");
    if (oldConnect) oldConnect.remove();

    const oldStatus = element("en96WCStatus");
    if (oldStatus) oldStatus.remove();

    const oldAddress = element("en96WCAddress");
    if (oldAddress) oldAddress.remove();

    const container = document.createElement("div");
    container.id = "en96WalletControls";

    // Step 1
    const setup = card(
      "🪙 1. إنشاء محفظة Stellar",
      "إذا لم تكن لديك محفظة، افتح LOBSTR " +
      "وأنشئ حسابك. سيظهر لك عنوان عام يبدأ بحرف G."
    );

    setup.appendChild(
      button(
        "📱 إنشاء / فتح محفظة LOBSTR",
        createWallet
      )
    );

    // Step 2
    const link = card(
      "🔗 2. ربط عنوان المحفظة بحساب EN96",
      "انسخ عنوان G العام من LOBSTR " +
      "وألصقه هنا، ثم احفظه في Supabase."
    );

    const field = document.createElement("input");
    field.id = "stellarAddress";
    field.className = "en96-simple-input";
    field.placeholder = "G...";
    field.maxLength = 56;
    field.spellcheck = false;
    field.autocomplete = "off";

    const save = button(
      "💾 حفظ عنوان G في EN96",
      saveAddress
    );

    save.id = "stellarSave";

    const saved = document.createElement("div");
    saved.id = "savedStellarAddress";
    saved.className = "en96-simple-address";

    const message = document.createElement("div");
    message.id = "stellarStatus";
    message.className = "en96-simple-status";
    message.textContent =
      "🔒 لم يتم إثبات ملكية المحفظة بعد.";

    link.append(field, save, saved, message);

    // Step 3
    const trust = card(
      "🛡️ 3. فتح خط الثقة EN96",
      "العملة: EN96 على Stellar Mainnet.\n" +
      "يجب إضافة العملة من داخل محفظة LOBSTR."
    );

    const issuer = document.createElement("div");
    issuer.className = "en96-simple-address";
    issuer.textContent = CONFIG.issuer;

    trust.appendChild(issuer);

    trust.appendChild(
      button(
        "📋 نسخ مُصدر EN96",
        copyIssuer,
        true
      )
    );

    trust.appendChild(
      button(
        "🪙 فتح LOBSTR لإضافة EN96",
        createWallet
      )
    );

    // Step 4
    const verify = card(
      "✅ 4. فحص جاهزية المحفظة",
      "نتحقق من وجود حساب Stellar " +
      "وخط الثقة الخاص بعملة EN96."
    );

    verify.appendChild(
      button(
        "🔍 التحقق من خط الثقة EN96",
        checkTrustline
      )
    );

    const warning = document.createElement("p");
    warning.textContent =
      "⚠️ حفظ عنوان G لا يثبت ملكيته. " +
      "السحب والشراء يحتاجان إلى تحقق إضافي " +
      "قبل تفعيل أي تحويل حقيقي.";

    verify.appendChild(warning);

    container.append(setup, link, trust, verify);

    wallet.appendChild(container);
  }

  // Public integration helpers
  window.EN96Wallet = Object.freeze({
    config: CONFIG,
    validStellarAddress: validAddress,
    checkTrustline,
    openLOBSTR: createWallet
  });

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
