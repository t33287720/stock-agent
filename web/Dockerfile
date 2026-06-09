FROM php:8.3-fpm-alpine

RUN apk add --no-cache nginx supervisor && \
    mkdir -p /run/nginx /tmp/sessions && \
    echo "clear_env = no" >> /usr/local/etc/php-fpm.d/www.conf

COPY docker/supervisord.conf /etc/supervisord.conf
COPY docker/nginx.conf       /etc/nginx/http.d/default.conf
COPY .                       /opt/stock/

WORKDIR /opt/stock
EXPOSE 80
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisord.conf"]
