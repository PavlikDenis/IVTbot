package main

import (
	"database/sql"
	"fmt"
	"log"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api/v5"
	_ "github.com/joho/godotenv/autoload"
	_ "github.com/mattn/go-sqlite3"
)

const (
	SpinCooldown = 1 * time.Second
	DBName       = "casino_stats.db"
)

var (
	Token = os.Getenv("BOT_TOKEN")

	Admins = []int64{5329886808}

	PointsByValue = map[int]int{
		22: 5,
		1:  10,
		43: 5,
		64: 20,
	}
)

var db *sql.DB

var (
	userCooldowns = make(map[int64]time.Time)
	cooldownMutex sync.Mutex
)

type User struct {
	UserID      int64
	FirstName   string
	Username    string
	TotalSpins  int
	TotalPoints int
	GrapeCount  int
	LemonCount  int
	BarCount    int
	SevenCount  int
}

// ---------- DB ----------

func initDB() {
	var err error

	db, err = sql.Open("sqlite3", DBName+"?_journal_mode=WAL&_busy_timeout=5000")
	if err != nil {
		log.Fatal(err)
	}

	_, err = db.Exec(`
	CREATE TABLE IF NOT EXISTS users (
		user_id INTEGER PRIMARY KEY,
		first_name TEXT,
		username TEXT,
		total_spins INTEGER DEFAULT 0,
		total_points INTEGER DEFAULT 0,
		grape_count INTEGER DEFAULT 0,
		lemon_count INTEGER DEFAULT 0,
		bar_count INTEGER DEFAULT 0,
		seven_count INTEGER DEFAULT 0,
		updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
	)`)
	if err != nil {
		log.Fatal(err)
	}

	_, err = db.Exec(`
	CREATE TABLE IF NOT EXISTS user_badges (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		user_id INTEGER,
		emoji TEXT
	)`)
	if err != nil {
		log.Fatal(err)
	}
}

func addUser(user *tgbotapi.User) {
	_, err := db.Exec(`
	INSERT INTO users(user_id, first_name, username)
	VALUES (?, ?, ?)
	ON CONFLICT(user_id) DO UPDATE SET
		first_name=excluded.first_name,
		username=excluded.username,
		updated_at=CURRENT_TIMESTAMP
	`, user.ID, user.FirstName, user.UserName)

	if err != nil {
		log.Println("addUser:", err)
	}
}

func addSpin(userID int64, value int, points int) {
	grape, bar, lemon, seven := 0, 0, 0, 0

	switch value {
	case 22:
		grape = 1
	case 1:
		bar = 1
	case 43:
		lemon = 1
	case 64:
		seven = 1
	}

	_, err := db.Exec(`
	UPDATE users
	SET total_spins = total_spins + 1,
		total_points = total_points + ?,
		grape_count = grape_count + ?,
		bar_count = bar_count + ?,
		lemon_count = lemon_count + ?,
		seven_count = seven_count + ?
	WHERE user_id = ?
	`, points, grape, bar, lemon, seven, userID)

	if err != nil {
		log.Println("addSpin:", err)
	}
}

func getLeaderboard(limit int) ([]User, error) {
	rows, err := db.Query(`
	SELECT first_name, username, total_spins, total_points
	FROM users
	ORDER BY total_points DESC
	LIMIT ?
	`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var users []User

	for rows.Next() {
		var u User
		if err := rows.Scan(&u.FirstName, &u.Username, &u.TotalSpins, &u.TotalPoints); err != nil {
			return nil, err
		}
		users = append(users, u)
	}
	return users, nil
}

func getUserStats(userID int64) (*User, error) {
	row := db.QueryRow(`
	SELECT total_spins, total_points,
		   grape_count, bar_count, lemon_count, seven_count
	FROM users
	WHERE user_id = ?
	`, userID)

	var u User
	u.UserID = userID

	err := row.Scan(
		&u.TotalSpins,
		&u.TotalPoints,
		&u.GrapeCount,
		&u.BarCount,
		&u.LemonCount,
		&u.SevenCount,
	)

	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}

	return &u, nil
}

func getUserBadges(userID int64) ([]string, error) {
	rows, err := db.Query("SELECT emoji FROM user_badges WHERE user_id = ?", userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var badges []string

	for rows.Next() {
		var emoji string
		if err := rows.Scan(&emoji); err != nil {
			return nil, err
		}
		badges = append(badges, emoji)
	}
	return badges, nil
}

func addBadge(userID int64, emoji string) error {
	_, err := db.Exec("INSERT INTO user_badges(user_id, emoji) VALUES (?, ?)", userID, emoji)
	return err
}

// ---------- LOGIC ----------

func handleDice(bot *tgbotapi.BotAPI, msg *tgbotapi.Message) {
	if msg == nil || msg.Dice == nil || msg.Dice.Emoji != "🎰" {
		return
	}

	userID := msg.From.ID
	now := time.Now()

	cooldownMutex.Lock()
	last, exists := userCooldowns[userID]
	if exists && now.Sub(last) < SpinCooldown {
		cooldownMutex.Unlock()

		bot.Request(tgbotapi.DeleteMessageConfig{
			ChatID:    msg.Chat.ID,
			MessageID: msg.MessageID,
		})
		return
	}
	userCooldowns[userID] = now
	cooldownMutex.Unlock()

	value := msg.Dice.Value
	points := PointsByValue[value]

	addUser(msg.From)
	addSpin(userID, value, points)
}

// ---------- COMMANDS ----------

func cmdLeaderboard(bot *tgbotapi.BotAPI, msg *tgbotapi.Message) {
	users, err := getLeaderboard(10)
	if err != nil {
		log.Println(err)
		return
	}

	text := "🏆 ТОП ИГРОКОВ\n\n"

	for i, u := range users {
		name := u.Username
		if name == "" {
			name = u.FirstName
		}

		text += fmt.Sprintf("%d. %s\n 🎰 %d вращений\n ⭐ %d очков\n\n",
			i+1, name, u.TotalSpins, u.TotalPoints)
	}

	bot.Send(tgbotapi.NewMessage(msg.Chat.ID, text))
}

func cmdMyStats(bot *tgbotapi.BotAPI, msg *tgbotapi.Message) {
	u, err := getUserStats(msg.From.ID)
	if err != nil || u == nil {
		bot.Send(tgbotapi.NewMessage(msg.Chat.ID, "Нет данных"))
		return
	}

	badges, _ := getUserBadges(msg.From.ID)

	name := msg.From.UserName
	if name == "" {
		name = msg.From.FirstName
	}

	text := fmt.Sprintf("📊 СТАТИСТИКА %s\n\n", name)

	if len(badges) > 0 {
		text += "🎖 Награды: " + strings.Join(badges, " ") + "\n\n"
	}

	text += fmt.Sprintf(
		"🍇🍇🍇: %d\n🍾🍾🍾: %d\n🍋🍋🍋: %d\n7️⃣7️⃣7️⃣: %d\n\n🎰 Всего: %d\n⭐ Очки: %d",
		u.GrapeCount, u.BarCount, u.LemonCount, u.SevenCount, u.TotalSpins, u.TotalPoints,
	)

	bot.Send(tgbotapi.NewMessage(msg.Chat.ID, text))
}

func cmdHelp(bot *tgbotapi.BotAPI, msg *tgbotapi.Message) {
	text := "📖 Команды:\n/top\n/mystats\n/help\n/givebadge"
	bot.Send(tgbotapi.NewMessage(msg.Chat.ID, text))
}

func cmdGiveBadge(bot *tgbotapi.BotAPI, msg *tgbotapi.Message) {
	isAdmin := false
	for _, a := range Admins {
		if msg.From.ID == a {
			isAdmin = true
		}
	}
	if !isAdmin {
		return
	}

	args := strings.Fields(msg.Text)
	if len(args) < 3 {
		bot.Send(tgbotapi.NewMessage(msg.Chat.ID, "Используй: /givebadge user_id emoji"))
		return
	}

	userID, _ := strconv.ParseInt(args[1], 10, 64)
	emoji := args[2]

	addBadge(userID, emoji)
	bot.Send(tgbotapi.NewMessage(msg.Chat.ID, "Выдано"))
}

// ---------- MAIN ----------

func main() {
	initDB()
	defer db.Close()

	bot, err := tgbotapi.NewBotAPI(Token)
	if err != nil {
		log.Fatal(err)
	}

	log.Println("Бот запущен:", bot.Self.UserName)

	u := tgbotapi.NewUpdate(0)
	u.Timeout = 60

	updates := bot.GetUpdatesChan(u)

	for update := range updates {
		if update.Message == nil {
			continue
		}

		msg := update.Message
		text := strings.ToLower(msg.Text)

		go func() {
			switch {
			case strings.HasPrefix(text, "/top"):
				cmdLeaderboard(bot, msg)
			case strings.HasPrefix(text, "/mystats"):
				cmdMyStats(bot, msg)
			case strings.HasPrefix(text, "/help"):
				cmdHelp(bot, msg)
			case strings.HasPrefix(text, "/givebadge"):
				cmdGiveBadge(bot, msg)
			default:
				handleDice(bot, msg)
			}
		}()
	}
}
