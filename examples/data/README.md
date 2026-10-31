# Example data

All files here are released under CC0 1.0 (public domain dedication) by their original publishers, or derived from CC0 data. You can use them for anything.

## Palmer Penguins (`penguins/`)

- `penguins.csv`: 344 penguins, tidy columns.
- `penguins_raw.csv`: the same birds as recorded in the field: long column names, units in headers, mixed-case values. Good for practicing cleanup.

Source: [allisonhorst/palmerpenguins](https://github.com/allisonhorst/palmerpenguins), `inst/extdata/`, package version 0.1.1. License: CC0. The data come from Palmer Station LTER and Dr. Kristen Gorman.

Citation: Horst AM, Hill AP, Gorman KB (2020). palmerpenguins: Palmer Archipelago (Antarctica) penguin data. R package version 0.1.0. https://allisonhorst.github.io/palmerpenguins/. doi: 10.5281/zenodo.3960218.

## NYC flights, 2013 (`nycflights13/`)

- `flights_2013_01.csv.gz`, `flights_2013_02.csv.gz`, `flights_2013_03.csv.gz`: every flight that left JFK, LGA or EWR in January to March 2013 (80,789 rows), one file per month.
- `weather_2013_q1.csv`: hourly weather at the three airports, January to March 2013.
- `airlines.csv`, `airports.csv`, `planes.csv`: lookup tables, unchanged.
- `carriers.json`: derived for this project. One object per airline, with a nested `fleet` list of the planes it flew in Q1 2013, joined from `flights` and `planes`. Use it to practice Explode List and Unnest JSON.

Source: [tidyverse/nycflights13](https://github.com/tidyverse/nycflights13), `data-raw/*.csv` and `data/flights.rda`. License: CC0. The original data come from the US Bureau of Transportation Statistics, NOAA, and the FAA.

Changes from the source: flights and weather are cut to January to March 2013. Flights were converted from R data to gzipped CSV, with whole-number columns written without decimals and `time_hour` written as ISO 8601 UTC.

Citation: Wickham H (2021). nycflights13: Flights that Departed NYC in 2013. https://github.com/tidyverse/nycflights13.
