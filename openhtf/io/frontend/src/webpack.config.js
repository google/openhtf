var webpack = require('webpack');
    path = require('path');

require('es6-promise').polyfill();


module.exports = {
  entry: {
    'vendor': './app/vendor',
    'app': './app/main'
  },
  output: {
    path: path.join(__dirname, 'dist'),
    filename: 'scripts/[name].bundle.js'
  },
  resolve: {
    extensions: ['', '.js', '.ts', '.styl']
  },
  devtool: 'source-map',
  devServer: {
    historyApiFallback: true
  },
  module: {
    loaders: [
      { test: /\.ts/,
        loaders: ['ts-loader'],
        exclude: /node_modules/
      },
      { test: /\.css/,
        loader: "style-loader!css-loader",
        exclude: /app/
      },
      { test: /\.(eot|woff|woff2|ttf)$/,
        loader: 'url-loader?limit=30000&name=/fonts/[name]-[hash].[ext]'
      },
      { test: /\.(svg|png|jpg)$/,
        loader: 'url-loader?limit=30000&name=/images/[name]-[hash].[ext]'
      },
      { test: /\.styl$/,
        loader: 'style-loader!css-loader!stylus-loader'
      }
    ]
  },
  plugins: [
    new webpack.optimize.CommonsChunkPlugin(
        /* chunkName= */'vendor',
        /* filename= */'scripts/vendor.bundle.js')
  ]
}
