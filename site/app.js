const DAY_NAMES = {
    monday: "Maanantai",
    tuesday: "Tiistai",
    wednesday: "Keskiviikko",
    thursday: "Torstai",
    friday: "Perjantai",
    saturday: "Lauantai",
    sunday: "Sunnuntai",
};

const JS_DAY_TO_KEY = [
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
];


function getSelectedDay() {
    const params = new URLSearchParams(window.location.search);
    const requestedDay = params.get("day")?.toLowerCase();

    if (requestedDay && DAY_NAMES[requestedDay]) {
        return requestedDay;
    }

    return JS_DAY_TO_KEY[new Date().getDay()];
}


function formatGeneratedAt(value) {
    if (!value) {
        return "";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return value;
    }

    return new Intl.DateTimeFormat("fi-FI", {
        dateStyle: "short",
        timeStyle: "short",
    }).format(date);
}


function createElement(tag, className, text) {
    const element = document.createElement(tag);

    if (className) {
        element.className = className;
    }

    if (text !== undefined && text !== null) {
        element.textContent = text;
    }

    return element;
}


function createRestaurantCard(restaurant, selectedDay) {
    const card = createElement(
        "article",
        "restaurant-card"
    );


    /*
     * Ravintolan otsikko
     */
    const header = createElement(
        "div",
        "restaurant-card-header"
    );

    header.appendChild(
        createElement(
            "h2",
            null,
            restaurant.name
        )
    );


    /*
     * Ravintolan metatiedot:
     * päivä, viikko ja osoite
     */
    const meta = createElement(
        "div",
        "restaurant-meta"
    );

    meta.appendChild(
        createElement(
            "span",
            "restaurant-date",
            DAY_NAMES[selectedDay] ?? selectedDay
        )
    );

    if (restaurant.week) {
        meta.appendChild(
            createElement(
                "span",
                null,
                restaurant.week
            )
        );
    }

    if (restaurant.address) {
        meta.appendChild(
            createElement(
                "span",
                null,
                restaurant.address
            )
        );
    }

    header.appendChild(meta);
    card.appendChild(header);


    /*
     * Ravintolan hinnat
     */
    if (
        Array.isArray(restaurant.prices) &&
        restaurant.prices.length > 0
    ) {
        const prices = createElement(
            "div",
            "restaurant-prices"
        );

        for (const price of restaurant.prices) {
            const priceText = [
                price.label,
                price.price
            ]
                .filter(Boolean)
                .join(" ");

            prices.appendChild(
                createElement(
                    "span",
                    "restaurant-price",
                    priceText
                )
            );
        }

        card.appendChild(prices);
    }


    /*
     * Valitaan vain tämän päivän ruokalista.
     */
    const meals =
        restaurant.days &&
        restaurant.days[selectedDay]
            ? restaurant.days[selectedDay]
            : [];


    /*
     * Jos kyseiselle päivälle
     * ei ole ruokalistaa.
     */
    if (meals.length === 0) {
        card.appendChild(
            createElement(
                "div",
                "meal",
                "Ei lounaslistaa tälle päivälle."
            )
        );
    } else {

        const list = createElement(
            "ul",
            "meal-list"
        );


        for (const meal of meals) {

            const item = createElement(
                "li",
                "meal"
            );


            /*
             * Annoksen nimi
             */
            item.appendChild(
                createElement(
                    "div",
                    "meal-name",
                    meal.name
                )
            );


            /*
             * Annoksen kuvaus.
             *
             * Tämä näkyy esimerkiksi
             * Street Canteenin eksoottisempien
             * ruokien kohdalla.
             */
            if (meal.description) {
                item.appendChild(
                    createElement(
                        "div",
                        "meal-description",
                        meal.description
                    )
                );
            }


            /*
             * Ruokavaliomerkinnät
             */
            if (
                Array.isArray(meal.diet) &&
                meal.diet.length > 0
            ) {

                const details = createElement(
                    "div",
                    "meal-details"
                );

                const diet = createElement(
                    "div",
                    "diet"
                );

                for (const tag of meal.diet) {
                    diet.appendChild(
                        createElement(
                            "span",
                            "diet-tag",
                            tag
                        )
                    );
                }

                details.appendChild(diet);
                item.appendChild(details);
            }


            list.appendChild(item);
        }


        card.appendChild(list);
    }


    /*
     * Linkki alkuperäiseen ruokalistaan
     */
    if (restaurant.source) {

        const footer = createElement(
            "div",
            "restaurant-footer"
        );

        const link = createElement(
            "a",
            "restaurant-source",
            "Avaa ravintolan alkuperäinen lounaslista"
        );

        link.href = restaurant.source;
        link.target = "_blank";
        link.rel = "noopener noreferrer";

        footer.appendChild(link);
        card.appendChild(footer);
    }


    return card;
}


async function loadLunchMenus() {

    const root =
        document.getElementById("restaurants");

    const updated =
        document.getElementById("updated");


    /*
     * Jos HTML:stä puuttuu restaurants-elementti,
     * ei voida renderöidä kortteja.
     */
    if (!root) {
        console.error(
            'Element with id="restaurants" was not found.'
        );

        return;
    }


    const selectedDay =
        getSelectedDay();


    try {

        /*
         * Haetaan GitHub Actionsin
         * generoima lunch.json.
         */
        const response = await fetch(
            "./data/lunch.json",
            {
                cache: "no-store"
            }
        );


        if (!response.ok) {
            throw new Error(
                `lunch.json returned HTTP ${response.status}`
            );
        }


        const data =
            await response.json();


        /*
         * Sivun yläosan päivitysaika.
         */
        if (updated) {

            const generated =
                formatGeneratedAt(
                    data.generated_at
                );

            const dayName =
                DAY_NAMES[selectedDay] ??
                selectedDay;


            updated.textContent = generated
                ? `${dayName} · Päivitetty ${generated}`
                : dayName;
        }


        /*
         * Poistetaan HTML:ssä mahdollisesti
         * oleva "Ladataan..."-teksti.
         */
        root.replaceChildren();


        /*
         * Jos ravintoloita ei tullut JSON:ssa.
         */
        if (
            !Array.isArray(data.restaurants) ||
            data.restaurants.length === 0
        ) {

            root.appendChild(
                createElement(
                    "div",
                    "message",
                    "Lounaslistoja ei löytynyt."
                )
            );

            return;
        }


        /*
         * Luodaan ravintolakortti
         * jokaiselle ravintolalle.
         */
        for (const restaurant of data.restaurants) {

            root.appendChild(
                createRestaurantCard(
                    restaurant,
                    selectedDay
                )
            );
        }


    } catch (error) {

        console.error(
            "Lunch menu loading failed:",
            error
        );


        root.replaceChildren(
            createElement(
                "div",
                "message error-message",
                "Lounaslistojen lataaminen epäonnistui."
            )
        );


        if (updated) {
            updated.textContent = "";
        }
    }
}


/*
 * Käynnistetään vasta kun DOM
 * on kokonaan ladattu.
 */
document.addEventListener(
    "DOMContentLoaded",
    loadLunchMenus
);
