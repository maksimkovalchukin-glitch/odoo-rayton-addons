document.addEventListener("DOMContentLoaded", () => {

  const tg = window.Telegram?.WebApp || null;

  if (tg) {
    tg.expand();
    tg.ready();

    // Кнопка "Назад" повертає на головну
    tg.BackButton.show();
    tg.BackButton.onClick(() => {
      window.location.href = "../index.html";
    });
  }

  const cards = document.querySelectorAll(".type-card");

  cards.forEach(card => {

    card.addEventListener("click", () => {

      const target = card.dataset.target;

      if (!target) return;

      // невеликий візуальний ефект натискання
      card.classList.add("active");

      setTimeout(() => {
        window.location.href = target;
      }, 120);

    });

  });

});
