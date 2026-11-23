fetch("./data/lunch.json")
    .then(response => response.json())
    .then(data => {

        const root = document.getElementById("restaurants");

        data.restaurants.forEach(restaurant => {

            const section = document.createElement("section");

            const heading = document.createElement("h2");
            heading.textContent = restaurant.name;

            section.appendChild(heading);

            const list = document.createElement("ul");

            restaurant.meals.forEach(meal => {
                const item = document.createElement("li");
                item.textContent = meal;
                list.appendChild(item);
            });

            section.appendChild(list);
            root.appendChild(section);
        });

    });