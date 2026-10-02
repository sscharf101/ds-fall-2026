"""MovieLens Dashboard — Streamlit Community Cloud app.

Answers the four assignment questions against the MovieLens 100k dataset,
with interactive filters in the sidebar. Chart choices are deliberate (see the
"How these were built" expander at the bottom and BUILD_LOG.md).
"""

from __future__ import annotations

import os

import altair as alt
import pandas as pd
import streamlit as st

st.set_page_config(page_title="MovieLens Dashboard", page_icon="🎬", layout="wide")

# Find the CSV no matter where the app is run from (repo root on Streamlit Cloud,
# the app's own folder locally, etc.). First existing candidate wins.
_HERE = os.path.dirname(os.path.abspath(__file__))
_CANDIDATES = [
    os.path.join(_HERE, "data", "movie_ratings.csv"),   # Week-04.../data/movie_ratings.csv
    os.path.join(_HERE, "movie_ratings.csv"),           # next to app.py
    os.path.join("Week-04-Vibe-Coding-101", "data", "movie_ratings.csv"),
    "movie_ratings.csv",
]
DATA_PATH = next((p for p in _CANDIDATES if os.path.exists(p)), _CANDIDATES[0])


# --------------------------------------------------------------------------- #
# Data loading (cached so the 100k-row CSV is parsed once per session)
# --------------------------------------------------------------------------- #
@st.cache_data
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Return (ratings, ratings_by_genre, genre_list).

    ratings           — one row per rating event (100k rows).
    ratings_by_genre  — ratings exploded so each (rating, genre) pair is a row;
                        this is how a multi-genre movie contributes to every
                        genre it belongs to.
    genre_list        — sorted unique genres for the filter widget.
    """
    df = pd.read_csv(DATA_PATH)
    # genres is pipe-separated, e.g. "Crime|Film-Noir|Mystery|Thriller".
    df["genre_list"] = df["genres"].fillna("").str.split("|")
    exploded = df.explode("genre_list").rename(columns={"genre_list": "genre"})
    exploded = exploded[exploded["genre"].str.strip() != ""]
    genres = sorted(exploded["genre"].unique().tolist())
    return df, exploded, genres


ratings, by_genre, ALL_GENRES = load_data()

# Release-year bounds (year has a few NaNs; drop them for the slider range).
YEAR_MIN = int(ratings["year"].dropna().min())
YEAR_MAX = int(ratings["year"].dropna().max())


# --------------------------------------------------------------------------- #
# Sidebar controls
# --------------------------------------------------------------------------- #
st.sidebar.header("Filters")

sel_genres = st.sidebar.multiselect(
    "Genres", options=ALL_GENRES, default=ALL_GENRES,
    help="Limit every chart to movies tagged with at least one of these genres.",
)
if not sel_genres:  # guard against an empty selection
    sel_genres = ALL_GENRES

year_range = st.sidebar.slider(
    "Release year range", min_value=YEAR_MIN, max_value=YEAR_MAX,
    value=(YEAR_MIN, YEAR_MAX),
    help="Filters by the movie's RELEASE year (not when it was rated).",
)

min_ratings = st.sidebar.slider(
    "Minimum ratings per movie (floor for 'best movies')",
    min_value=10, max_value=300, value=50, step=10,
    help="A movie needs at least this many ratings to be eligible in Q4. "
         "The assignment asks you to compare 50 vs 150.",
)

st.sidebar.caption("Dataset: MovieLens 100k · 100,000 ratings · 1,682 movies")


# --------------------------------------------------------------------------- #
# Apply filters -> working frames used by the charts
# --------------------------------------------------------------------------- #
lo, hi = year_range
genre_set = set(sel_genres)

# Movie ids that belong to at least one selected genre.
movies_in_genres = by_genre.loc[by_genre["genre"].isin(genre_set), "movie_id"].unique()

year_ok = ratings["year"].between(lo, hi)
genre_ok = ratings["movie_id"].isin(movies_in_genres)
f_ratings = ratings[year_ok & genre_ok].copy()
f_by_genre = by_genre[
    by_genre["genre"].isin(genre_set) & by_genre["year"].between(lo, hi)
].copy()


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
st.title("🎬 MovieLens Dashboard")
st.markdown(
    "Four questions about the MovieLens 100k ratings, answered interactively. "
    "Use the sidebar to filter by genre, release year, and the ratings floor."
)

c1, c2, c3 = st.columns(3)
c1.metric("Ratings (filtered)", f"{len(f_ratings):,}")
c2.metric("Movies (filtered)", f"{f_ratings['movie_id'].nunique():,}")
c3.metric("Avg rating (filtered)", f"{f_ratings['rating'].mean():.2f}" if len(f_ratings) else "—")

st.divider()


# --------------------------------------------------------------------------- #
# Q1 — Genre breakdown
# --------------------------------------------------------------------------- #
st.header("Q1 · Genre breakdown")
st.caption(
    "Distribution of genres among the **movies that were rated** (unique movies, "
    "not rating events). Each movie is counted once in *every* genre it lists, so "
    "the totals sum to more than the number of movies — that's expected with "
    "multi-genre films."
)

# Unique movies within the current filters, then explode to genres and count.
uniq_movies = (
    f_ratings[["movie_id", "genres"]].drop_duplicates("movie_id").copy()
)
uniq_movies["genre"] = uniq_movies["genres"].fillna("").str.split("|")
q1 = uniq_movies.explode("genre")
q1 = q1[q1["genre"].isin(genre_set) & (q1["genre"].str.strip() != "")]
q1_counts = (
    q1.groupby("genre").size().reset_index(name="movies").sort_values("movies", ascending=False)
)

if len(q1_counts):
    chart_q1 = (
        alt.Chart(q1_counts)
        .mark_bar(color="#4c78a8")
        .encode(
            x=alt.X("movies:Q", title="Number of movies"),
            y=alt.Y("genre:N", sort="-x", title=None),
            tooltip=["genre", "movies"],
        )
        .properties(height=460)
    )
    st.altair_chart(chart_q1, use_container_width=True)
else:
    st.info("No movies match the current filters.")

st.divider()


# --------------------------------------------------------------------------- #
# Q2 — Genre satisfaction (avg rating by genre)
# --------------------------------------------------------------------------- #
st.header("Q2 · Which genres are rated highest / lowest?")
st.caption(
    "Average rating per genre, computed across **rating events** (every rating a "
    "movie received contributes to each of its genres). Sorted high → low."
)

q2 = (
    f_by_genre.groupby("genre")["rating"]
    .agg(avg_rating="mean", n="size")
    .reset_index()
    .sort_values("avg_rating", ascending=False)
)

if len(q2):
    chart_q2 = (
        alt.Chart(q2)
        .mark_bar()
        .encode(
            x=alt.X("avg_rating:Q", title="Average rating",
                    scale=alt.Scale(domain=[0, 5])),
            y=alt.Y("genre:N", sort="-x", title=None),
            color=alt.Color("avg_rating:Q", scale=alt.Scale(scheme="blues"),
                            legend=None),
            tooltip=["genre",
                     alt.Tooltip("avg_rating:Q", format=".2f", title="avg rating"),
                     alt.Tooltip("n:Q", format=",", title="# ratings")],
        )
        .properties(height=460)
    )
    st.altair_chart(chart_q2, use_container_width=True)
    best, worst = q2.iloc[0], q2.iloc[-1]
    st.markdown(
        f"**Highest:** {best.genre} ({best.avg_rating:.2f}) · "
        f"**Lowest:** {worst.genre} ({worst.avg_rating:.2f})"
    )
else:
    st.info("No ratings match the current filters.")

st.divider()


# --------------------------------------------------------------------------- #
# Q3 — Mean rating across movie release years
# --------------------------------------------------------------------------- #
st.header("Q3 · Mean rating across release years")
st.caption(
    "Mean rating grouped by the movie's **release year** (`year`), not the year "
    "it was rated. A line chart is the right form for a trend over time."
)

q3 = (
    f_ratings.dropna(subset=["year"])
    .groupby(f_ratings["year"].astype("Int64"))["rating"]
    .agg(mean_rating="mean", n="size")
    .reset_index()
    .rename(columns={"year": "release_year"})
)
q3["release_year"] = q3["release_year"].astype(int)

if len(q3):
    line = (
        alt.Chart(q3)
        .mark_line(point=True, color="#e45756")
        .encode(
            x=alt.X("release_year:Q", title="Release year",
                    axis=alt.Axis(format="d")),
            y=alt.Y("mean_rating:Q", title="Mean rating",
                    scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("release_year:Q", title="year", format="d"),
                     alt.Tooltip("mean_rating:Q", format=".2f", title="mean"),
                     alt.Tooltip("n:Q", format=",", title="# ratings")],
        )
        .properties(height=400)
    )
    st.altair_chart(line, use_container_width=True)
    st.caption(
        "⚠️ Early years have very few ratings, so those points are noisy — "
        "hover to see the sample size behind each year."
    )
else:
    st.info("No ratings match the current filters.")

st.divider()


# --------------------------------------------------------------------------- #
# Q4 — Best movies, with a ratings floor
# --------------------------------------------------------------------------- #
st.header("Q4 · Top 5 movies (with a ratings floor)")
st.caption(
    "Highest average rating among movies with **at least the floor** number of "
    "ratings (set in the sidebar). Without a floor, obscure movies with one "
    "perfect rating would dominate — the floor is what makes 'best' meaningful."
)


def top5(df: pd.DataFrame, floor: int) -> pd.DataFrame:
    agg = (
        df.groupby(["movie_id", "title"])["rating"]
        .agg(avg_rating="mean", n="size")
        .reset_index()
    )
    agg = agg[agg["n"] >= floor]
    return agg.sort_values(["avg_rating", "n"], ascending=[False, False]).head(5)


q4 = top5(f_ratings, min_ratings)
st.markdown(f"**Floor = {min_ratings} ratings** — {len(q4)} shown")

if len(q4):
    chart_q4 = (
        alt.Chart(q4)
        .mark_bar(color="#54a24b")
        .encode(
            x=alt.X("avg_rating:Q", title="Average rating",
                    scale=alt.Scale(domain=[0, 5])),
            y=alt.Y("title:N", sort="-x", title=None),
            tooltip=["title",
                     alt.Tooltip("avg_rating:Q", format=".2f", title="avg rating"),
                     alt.Tooltip("n:Q", format=",", title="# ratings")],
        )
        .properties(height=260)
    )
    st.altair_chart(chart_q4, use_container_width=True)
    st.dataframe(
        q4.rename(columns={"title": "Movie", "avg_rating": "Avg rating", "n": "# ratings"})
          .assign(**{"Avg rating": lambda d: d["Avg rating"].round(2)})
          [["Movie", "Avg rating", "# ratings"]],
        hide_index=True, use_container_width=True,
    )
else:
    st.info(f"No movies have at least {min_ratings} ratings under the current filters.")

# The assignment explicitly asks: what changes from a floor of 50 to 150?
with st.expander("Compare floor = 50 vs floor = 150"):
    a, b = st.columns(2)
    t50, t150 = top5(f_ratings, 50), top5(f_ratings, 150)
    with a:
        st.markdown("**Floor = 50**")
        st.dataframe(
            t50.assign(avg_rating=lambda d: d.avg_rating.round(2))
               [["title", "avg_rating", "n"]]
               .rename(columns={"title": "Movie", "avg_rating": "Avg", "n": "#"}),
            hide_index=True, use_container_width=True,
        )
    with b:
        st.markdown("**Floor = 150**")
        st.dataframe(
            t150.assign(avg_rating=lambda d: d.avg_rating.round(2))
                [["title", "avg_rating", "n"]]
                .rename(columns={"title": "Movie", "avg_rating": "Avg", "n": "#"}),
            hide_index=True, use_container_width=True,
        )
    gained = set(t150["title"]) - set(t50["title"])
    dropped = set(t50["title"]) - set(t150["title"])
    st.markdown(
        "Raising the floor filters out movies that only *looked* great on a thin "
        "sample. "
        + (f"New at 150: {', '.join(sorted(gained))}. " if gained else "")
        + (f"Dropped from the top 5: {', '.join(sorted(dropped))}." if dropped else "")
    )

st.divider()


# --------------------------------------------------------------------------- #
# Method notes
# --------------------------------------------------------------------------- #
with st.expander("How these charts were built (method notes)"):
    st.markdown(
        """
- **Multi-genre handling (Q1 & Q2):** the `genres` field is pipe-separated
  (`Crime|Film-Noir|Mystery|Thriller`). I split it and *exploded* the data so a
  movie counts once in **each** of its genres. Q1 counts **unique movies**
  (deduped on `movie_id`); Q2 averages over **rating events**.
- **Release year vs rating year (Q3):** `year` is when the movie came out;
  `rating_year` is only 1997–1998. "Across release years" uses `year`.
- **Chart choices:** sorted horizontal bars for the 18-genre breakdown (a pie
  with 18 slices is unreadable), a line for the time trend, and a floored,
  sorted bar + table for the top-5.
- **The floor (Q4):** without a minimum rating count, one-off perfect scores win.
  The slider lets you move the floor; the expander contrasts 50 vs 150.
        """
    )
