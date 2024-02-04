import os
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
import datetime
from collections import defaultdict

from helpers import apology, login_required, lookup, usd, available_shares, sort_history

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # selecting only those shares for which number of shares(buy - sell) > 0
    portfolio = db.execute(
        "SELECT * FROM (SELECT symbol, SUM(shares) as shares_sum FROM transactions WHERE person_id = ? GROUP BY SYMBOL ORDER BY SYMBOL) WHERE shares_sum > 0 ",
        session["user_id"],
    )
    # selecting available cash
    cash = db.execute("SELECT cash from users WHERE id = ?", session["user_id"])
    total = 0
    for row in portfolio:
        look = lookup(row["symbol"])
        price = float(look["price"])  # looking up current price of each stock
        row["price"] = price
        row["value"] = price * float(row["shares_sum"])
        total += row["value"]
    total += cash[0]["cash"]  # total includes available cash as well
    return render_template(
        "index.html", portfolio=portfolio, cash=cash[0]["cash"], total=total
    )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    elif request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")
        look = lookup(symbol)
        ct = datetime.datetime.now()

        if not symbol or not shares:
            return apology("All field is necessary", 400)
        elif look == None:
            return apology("Stock symbol is incorrect", 400)
        elif (
            shares.isdigit() == False
        ):  # check50 is so bad this week -> checking if numeric value or not
            return apology("bruh cat", 400)

        # checking if user can afford the input number of shares
        price = float(look["price"])
        total = price * float(shares)
        balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        if float(shares) <= 0:
            return apology("Number of shares must be greater than zero", 400)
        elif total > balance[0]["cash"]:
            return apology("Not enough cash", 400)

        db.execute(
            "UPDATE users SET cash = cash - ? WHERE id = ? ", total, session["user_id"]
        )
        db.execute(
            "INSERT INTO transactions(person_id, symbol, price_at_transaction, shares, date) VALUES(?,?,?,?,?)",
            session["user_id"],
            symbol,
            price,
            shares,
            ct,
        )  # new table that will store id of users and info of stocks they have bought
        return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = db.execute(
        "SELECT symbol, shares, date FROM transactions WHERE person_id = ?",
        session["user_id"],
    )
    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")

    if request.method == "POST":
        symbol = request.form.get("symbol")
        quote = lookup(symbol)
        if quote == None:
            return apology("Symbol doesn't match")
        else:
            return render_template("quoted.html", quotes=quote)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")

    if request.method == "POST":
        name = request.form.get("username")
        password = generate_password_hash(
            request.form.get("password"), method="pbkdf2", salt_length=16
        )  # storing password in hash form
        confirm_password = request.form.get("confirmation")

        # searching if previous user exist with the same username
        previous = db.execute("SELECT * from users WHERE username = ? ", name)

        if not name:
            return apology("must provide a username", 400)
        elif not password or not confirm_password:
            return apology("must provide a password", 400)
        elif (check_password_hash(password, confirm_password)) == False:
            return apology("password doesn't match", 400)
        elif len(previous) > 0:
            return apology("username is already taken", 400)
        else:
            db.execute("INSERT INTO users (username,hash) VALUES (?,?)", name, password)
            return render_template("login.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":
        # this is necessary so that drop down has the opttion of owned stocks only
        portfolio = db.execute(
            "SELECT * FROM (SELECT symbol, SUM(shares) as shares_sum FROM transactions WHERE person_id = ? GROUP BY SYMBOL ORDER BY SYMBOL) WHERE shares_sum > 0 ",
            session["user_id"],
        )
        return render_template("sell.html", options=portfolio)

    elif request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")
        look = lookup(symbol)
        ct = datetime.datetime.now()

        if not symbol or not shares:
            return apology("All field is necessary", 400)
        elif (
            shares.isdigit() == False
        ):  # check50 is so bad this week -> checking if numeric value or not
            return apology("bruh cat", 400)

        # calculating price to be added to user account
        price = float(look["price"])
        total = price * float(shares)

        portfolio = db.execute(
            "SELECT * FROM (SELECT symbol, SUM(shares) as shares_sum FROM transactions WHERE person_id = ? GROUP BY SYMBOL ORDER BY SYMBOL) WHERE shares_sum > 0 ",
            session["user_id"],
        )

        if float(shares) <= 0:
            return apology("Number of shares must be greater than zero", 400)
        found = False  # boolean variable to check if user actually owns that stock
        for x in portfolio:
            if x["symbol"] == symbol:
                found = True
                if x["shares_sum"] < float(shares):
                    return apology("You donot have enough number of shares", 400)
        if found == False:
            return apology("You donot own this share", 400)

        # storing sell transaction in negative form
        price = -abs(price)
        shares = -abs(float(shares))
        db.execute(
            "UPDATE users SET cash = cash + ? WHERE id = ? ", total, session["user_id"]
        )
        db.execute(
            "INSERT INTO transactions(person_id, symbol, price_at_transaction, shares, date) VALUES(?,?,?,?,?)",
            session["user_id"],
            symbol,
            price,
            shares,
            ct,
        )  # new table that will store id of users and info of stocks they have bought
        return redirect("/")
