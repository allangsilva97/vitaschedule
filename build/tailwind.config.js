// Mesma configuração que antes ficava inline no HTML (tailwind.config = {...}).
// O build.js grava em ./.tmp/source.html uma cópia do HTML SEM o <style> embutido; assim o CSS antigo
// não "realimenta" o scanner de classes (classes removidas do HTML deixam de ser geradas).
module.exports = {
  content: ['./.tmp/source.html'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#ecfdf5',
          100: '#d1fae5',
          500: '#10b981',
          600: '#059669',
          700: '#047857',
        },
      },
    },
  },
};
