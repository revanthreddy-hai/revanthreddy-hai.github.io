const coverFallback = (book) => {
  const fallback = document.createElement("span");
  fallback.className = "book-cover-fallback";
  fallback.textContent = book.title.trim().charAt(0).toUpperCase() || "•";
  return fallback;
};

const createBookCard = (book, index) => {
  const item = document.createElement("li");
  const link = document.createElement("a");
  const cover = document.createElement("span");
  const title = document.createElement("strong");
  const author = document.createElement("small");

  item.className = "book-card";
  link.className = "book-card-link";
  link.href = book.url;
  link.title = `${book.title} — ${book.author}`;
  cover.className = "book-cover";
  cover.setAttribute("aria-hidden", "true");
  title.className = "book-title";
  author.className = "book-author";
  title.textContent = book.title;
  author.textContent = book.author;

  if (book.image) {
    const image = document.createElement("img");
    image.src = book.image;
    image.alt = "";
    image.width = 200;
    image.height = 300;
    image.decoding = "async";
    image.loading = index < 12 ? "eager" : "lazy";
    image.addEventListener("error", () => cover.replaceChildren(coverFallback(book)), { once: true });
    cover.append(image);
  } else {
    cover.append(coverFallback(book));
  }

  link.append(cover, title, author);
  item.append(link);
  return item;
};

const renderShelf = (list, message, books) => {
  if (!books.length) {
    message.textContent = "No books on this shelf.";
    return;
  }

  const fragment = document.createDocumentFragment();
  books.forEach((book, index) => fragment.append(createBookCard(book, index)));
  list.append(fragment);
  list.hidden = false;
  message.hidden = true;
};

const renderReadGroups = (container, message, groups) => {
  const total = groups.reduce((count, group) => count + group.books.length, 0);
  if (!total) {
    message.textContent = "No books on this shelf.";
    return 0;
  }

  const fragment = document.createDocumentFragment();
  let bookIndex = 0;

  groups.forEach((group) => {
    const section = document.createElement("section");
    const heading = document.createElement("h3");
    const count = document.createElement("span");
    const list = document.createElement("ul");

    section.className = "shelf-group";
    heading.className = "shelf-group-title";
    count.textContent = `(${group.books.length})`;
    list.className = "cover-grid";
    heading.append(group.name, count);

    group.books.forEach((book) => {
      list.append(createBookCard(book, bookIndex));
      bookIndex += 1;
    });

    section.append(heading, list);
    fragment.append(section);
  });

  container.append(fragment);
  container.hidden = false;
  message.hidden = true;
  return total;
};

const showShelf = (shelf) => {
  const showingRead = shelf === "read";
  document.querySelector("#read-tab").setAttribute("aria-pressed", String(showingRead));
  document.querySelector("#current-tab").setAttribute("aria-pressed", String(!showingRead));
  document.querySelector("#read-panel").hidden = !showingRead;
  document.querySelector("#current-panel").hidden = showingRead;
};

const loadBooks = async () => {
  const response = await fetch("data/books.json", { cache: "no-store" });
  if (!response.ok) throw new Error("Could not load the book shelf.");

  const data = await response.json();
  const readGroups = data.readGroups ?? [];
  const currentlyReading = data.currentlyReading ?? [];

  const readCount = renderReadGroups(
    document.querySelector("#read-shelf"),
    document.querySelector("#read-message"),
    readGroups
  );
  renderShelf(
    document.querySelector("#current-shelf"),
    document.querySelector("#current-message"),
    currentlyReading
  );
  document.querySelector("#read-count").textContent = `(${readCount})`;
  document.querySelector("#current-count").textContent = `(${currentlyReading.length})`;

};

document.querySelectorAll("[data-shelf]").forEach((button) => {
  button.addEventListener("click", () => showShelf(button.dataset.shelf));
});

loadBooks().catch(() => {
  document.querySelector("#read-message").textContent = "The shelf could not be loaded.";
  document.querySelector("#current-message").textContent = "The shelf could not be loaded.";
  document.querySelector("#books-source").textContent = "Goodreads could not be reached.";
});
