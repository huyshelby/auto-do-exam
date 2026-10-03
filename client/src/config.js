/**
 * Cấu hình selector CSS và tham số kết nối cho Quiz Agent
 */
export const CONFIG = {
  // Local RAG Server Endpoint
  SERVER_URL: 'http://127.0.0.1:8000/solve',

  // CSS Selectors nhận diện thành phần câu hỏi
  SELECTORS: {
    QUESTION: '.question-text, .quiz-question, #questionTitle, .question-content',
    OPTION_CONTAINER: '.answers-list, .options-group, .choices',
    OPTION_ITEM: '.option-item, .answer-choice, label.radio, .answer-item',
    SUBMIT_BUTTON: '#btnSubmit, .btn-submit, .btn-next, button[type="submit"]',
  },

  // Tùy chọn tự động submit sau khi chọn đáp án
  AUTO_SUBMIT: false,
  AUTO_SUBMIT_DELAY_MS: 1500,

  // Tham số nhịp độ đọc (Human Pacing)
  PACING: {
    MIN_DELAY_MS: 3000,
    MAX_DELAY_MS: 6000,
    WORDS_PER_SEC_MEAN: 3.5,
    WORDS_PER_SEC_STD: 0.4,
    DECISION_TIME_MEAN_MS: 1200,
    DECISION_TIME_STD_MS: 200,
  }
};
