registerPlugin({
  install: function(less, pluginManager, functions) {
    functions.add('random', function(input) {
      return new(less.tree.Anonymous)(Math.floor(Math.random() * (input.value - 0) + 0));
    });
  },
});